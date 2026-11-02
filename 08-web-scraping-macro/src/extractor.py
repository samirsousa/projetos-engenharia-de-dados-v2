"""
Componente 1: Extrator Robusto de Web Scraping Ético com Tratamento de Exceções e Retry Logic.

Características de Engenharia:
- Verificação prévia de conformidade com `robots.txt` (`urllib.robotparser`).
- Identificação transparente via `User-Agent` e *Rate Limiting* (politeness delay).
- Motor de Retentativas (`RetryWithExponentialBackoff`) para falhas transitórias (HTTP 429/502/503/504, Timeouts).
- Parser HTML DOM nativo (`html.parser.HTMLParser`) para extração estruturada de tabelas públicas.
- Persistência na Camada Bronze (`data/bronze_raw/`) com hash `SHA-256` do conteúdo bruto.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

from src.config import ScrapingPipelineConfig, setup_logger
from src.portal_simulator import materialize_mock_portal

logger = setup_logger("Macro-Extractor")

T = TypeVar("T")


class ScrapingException(Exception):
    """Exceção base para erros de extração Web Scraping."""


class TransientScrapeError(ScrapingException):
    """Falha temporária de rede ou servidor (elegível para Retry com Backoff Exponencial)."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PermanentScrapeError(ScrapingException):
    """Falha permanente (HTTP 403/404 ou bloqueio por robots.txt — não elegível para Retry)."""


class RobotsTxtDisallowedError(PermanentScrapeError):
    """Levantada quando o caminho alvo é proibido pelas diretivas do robots.txt."""


@dataclass
class RawScrapedRow:
    """Registro bruto extraído diretamente das células `<td>` da tabela HTML."""

    source_page: str
    series_id: str
    raw_indicator_code: str
    raw_indicator_name: str
    raw_institution: str
    raw_reference_date: str
    raw_value_str: str
    raw_unit: str
    raw_frequency: str
    raw_status: str
    scraped_at_utc: str


@dataclass
class ExtractionBatchResult:
    """Metadados e payload resultantes de uma sessão de extração na Camada Bronze."""

    batch_id: str
    extracted_at_utc: str
    pages_scraped: int
    total_raw_rows: int
    total_retry_attempts: int
    bronze_file_path: str
    payload_sha256: str
    rows: List[RawScrapedRow] = field(default_factory=list)


class MacroHTMLTableParser(HTMLParser):
    """Parser DOM em Python puro para extrair linhas de `<table id='macro-indicators-table'>`."""

    def __init__(self, source_page: str, scraped_at_utc: str) -> None:
        super().__init__()
        self.source_page = source_page
        self.scraped_at_utc = scraped_at_utc
        self.in_target_table = False
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.current_series_id = ""
        self.current_cells: List[str] = []
        self.current_cell_buffer: List[str] = []
        self.extracted_rows: List[RawScrapedRow] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attr_dict = dict(attrs)
        if tag == "table" and attr_dict.get("id") == "macro-indicators-table":
            self.in_target_table = True
        elif self.in_target_table and tag == "tbody":
            self.in_tbody = True
        elif self.in_tbody and tag == "tr":
            self.in_tr = True
            self.current_series_id = str(attr_dict.get("data-series") or "")
            self.current_cells = []
        elif self.in_tr and tag == "td":
            self.in_td = True
            self.current_cell_buffer = []

    def handle_data(self, data: str) -> None:
        if self.in_td:
            self.current_cell_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.in_td:
            self.in_td = False
            self.current_cells.append("".join(self.current_cell_buffer))
        elif tag == "tr" and self.in_tr:
            self.in_tr = False
            if len(self.current_cells) >= 8:
                self.extracted_rows.append(
                    RawScrapedRow(
                        source_page=self.source_page,
                        series_id=self.current_series_id,
                        raw_indicator_code=self.current_cells[0],
                        raw_indicator_name=self.current_cells[1],
                        raw_institution=self.current_cells[2],
                        raw_reference_date=self.current_cells[3],
                        raw_value_str=self.current_cells[4],
                        raw_unit=self.current_cells[5],
                        raw_frequency=self.current_cells[6],
                        raw_status=self.current_cells[7],
                        scraped_at_utc=self.scraped_at_utc,
                    )
                )
        elif tag == "tbody" and self.in_tbody:
            self.in_tbody = False
        elif tag == "table" and self.in_target_table:
            self.in_target_table = False


class MacroWebExtractor:
    """
    Extrator Web Scraping ético com verificação de `robots.txt` e
    retentativas automáticas via Exponential Backoff + Jitter.
    """

    def __init__(
        self,
        config: Optional[ScrapingPipelineConfig] = None,
        simulate_transient_failures: int = 1,
    ) -> None:
        self.config = config or ScrapingPipelineConfig()
        self.config.ensure_directories()
        self.simulate_transient_failures = simulate_transient_failures
        self._remaining_simulated_failures = simulate_transient_failures
        self.total_retries_triggered = 0
        self.rng = random.Random(42)

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def verify_robots_txt(self, robots_txt_content: str, target_path: str) -> bool:
        """Valida se o User-Agent do extrator tem permissão ética no robots.txt."""
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(robots_txt_content.splitlines())
        allowed = rp.can_fetch(self.config.user_agent, target_path)
        if not allowed:
            raise RobotsTxtDisallowedError(
                f"Acesso bloqueado pelas diretivas éticas do robots.txt para o caminho: {target_path}"
            )
        return True

    def execute_with_retry(self, operation_name: str, func: Callable[[], T]) -> T:
        """
        Executa uma função de rede/extração com política de Retry e Exponential Backoff + Jitter.
        Apenas `TransientScrapeError` dispara novas tentativas; `PermanentScrapeError` falha imediatamente.
        """
        attempt = 0
        max_retries = self.config.max_retries

        while True:
            attempt += 1
            try:
                return func()
            except PermanentScrapeError:
                logger.error(
                    "Erro permanente em '%s' (tentativa %d). Abortando sem retry.",
                    operation_name,
                    attempt,
                )
                raise
            except TransientScrapeError as exc:
                if attempt > max_retries:
                    logger.error(
                        "Exauridas todas as %d retentativas para '%s'. Último erro: %s",
                        max_retries,
                        operation_name,
                        exc,
                    )
                    raise

                self.total_retries_triggered += 1
                backoff = min(
                    self.config.backoff_Max_sec,
                    self.config.backoff_base_sec * (2 ** (attempt - 1)),
                )
                jitter = self.rng.uniform(0.01, 0.05)
                sleep_sec = round(backoff + jitter, 3)

                logger.warning(
                    "Falha transitória em '%s' (tentativa %d/%d) | Status=%s | Erro='%s' | "
                    "Aguardando %.3fs (Exponential Backoff + Jitter) antes de tentar novamente...",
                    operation_name,
                    attempt,
                    max_retries,
                    exc.status_code or "TIMEOUT",
                    exc,
                    sleep_sec,
                )
                time.sleep(sleep_sec)

    def _fetch_html_document(self, page_path: Path, robots_content: str) -> str:
        """Lê ou requisita a página HTML aplicando validação de robots.txt e simulação de falhas."""
        relative_url = f"/{page_path.name}"
        self.verify_robots_txt(robots_content, relative_url)

        def _do_request() -> str:
            if self._remaining_simulated_failures > 0:
                self._remaining_simulated_failures -= 1
                raise TransientScrapeError(
                    f"HTTP 503 Service Unavailable ao requisitar {relative_url} (Gateway sobrecarregado)",
                    status_code=503,
                )

            if not page_path.exists():
                raise PermanentScrapeError(f"HTTP 404 Not Found: Recurso '{relative_url}' inexistente.")

            # Rate-limiting ético entre requisições
            if self.config.rate_limit_delay_sec > 0:
                time.sleep(self.config.rate_limit_delay_sec)

            return page_path.read_text(encoding="utf-8")

        return self.execute_with_retry(f"GET {relative_url}", _do_request)

    def run_extraction(self, batch_id: Optional[str] = None) -> ExtractionBatchResult:
        """
        Executa a extração completa das páginas HTML públicas, aplica o parser DOM
        e salva o lote bruto na camada Bronze (`data/bronze_raw/`).
        """
        robots_path, boletim_path, ptax_path = materialize_mock_portal(self.config)
        robots_content = robots_path.read_text(encoding="utf-8")

        now_utc = self._utc_now()
        now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        resolved_batch_id = batch_id or f"SCRAPE-{now_utc.strftime('%Y%m%d_%H%M%S')}"

        logger.info(
            "Iniciando extração Web Scraping Ético | batch_id=%s | User-Agent='%s'",
            resolved_batch_id,
            self.config.user_agent[:48] + "...",
        )

        target_pages = [boletim_path, ptax_path]
        all_rows: List[RawScrapedRow] = []

        for page_path in target_pages:
            html_text = self._fetch_html_document(page_path, robots_content)
            parser = MacroHTMLTableParser(source_page=page_path.name, scraped_at_utc=now_iso)
            parser.feed(html_text)
            logger.info(
                "Página extraída com sucesso | pagina=%s | linhas_dom=%d",
                page_path.name,
                len(parser.extracted_rows),
            )
            all_rows.extend(parser.extracted_rows)

        serialized_rows = [asdict(r) for r in all_rows]
        payload_bytes = json.dumps(serialized_rows, sort_keys=True, ensure_ascii=False).encode("utf-8")
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

        bronze_filename = f"raw_macro_indicators_{resolved_batch_id}.json"
        bronze_path = self.config.bronze_raw_dir / bronze_filename
        latest_bronze_path = self.config.bronze_raw_dir / "latest_bronze_extraction.json"

        envelope = {
            "batch_id": resolved_batch_id,
            "extracted_at_utc": now_iso,
            "user_agent": self.config.user_agent,
            "pages_scraped": len(target_pages),
            "total_raw_rows": len(all_rows),
            "total_retry_attempts": self.total_retries_triggered,
            "payload_sha256": payload_hash,
            "rows": serialized_rows,
        }

        for target_out in (bronze_path, latest_bronze_path):
            with open(target_out, "w", encoding="utf-8") as fh:
                json.dump(envelope, fh, indent=2, ensure_ascii=False)

        logger.info(
            "Extração Bronze concluída | arquivo=%s | total_linhas=%d | retries_acionados=%d | sha256=%s...",
            bronze_filename,
            len(all_rows),
            self.total_retries_triggered,
            payload_hash[:12],
        )

        return ExtractionBatchResult(
            batch_id=resolved_batch_id,
            extracted_at_utc=now_iso,
            pages_scraped=len(target_pages),
            total_raw_rows=len(all_rows),
            total_retry_attempts=self.total_retries_triggered,
            bronze_file_path=str(bronze_path),
            payload_sha256=payload_hash,
            rows=all_rows,
        )
