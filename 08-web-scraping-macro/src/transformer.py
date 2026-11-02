"""
Componente 2: Transformador de Dados Macroeconômicos (Limpeza, Normalização e Schema Tipado).

Responsabilidades de Engenharia:
- Limpeza de ruídos de HTML: notas de rodapé `(*)`, `[1]`, `[preliminar]`, símbolos `R$`, `% a.a.`, `pts`.
- Conversão de notação numérica brasileira (`1.234,56` -> `1234.56`) para `float` IEEE-754.
- Padronização de datas heterogêneas (`DD/MM/YYYY` e `YYYY-MM-DD`) para ISO-8601 (`YYYY-MM-DD`).
- Filtragem e quarentena de linhas sem divulgação (`N/D`, `-`).
- Aplicação de schema estritamente tipado (`TypedMacroIndicator`) e gravação na Camada Silver.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import ScrapingPipelineConfig, setup_logger

logger = setup_logger("Macro-Transformer")

FOOTNOTE_REGEX = re.compile(r"(\(\*\)|\[\d+\]|\[preliminar\]|do PIB|a\.a\.|a\.m\.|pts|R\$|US\$|%)", re.IGNORECASE)
MISSING_TOKENS = {"n/d", "nd", "-", "...", "", "null", "none"}

ALLOWED_UNITS = {"PCT_AA", "PCT_12M", "PCT_AM", "PCT_PEA", "INDEX_PTS", "PCT_PIB", "BRL", "USD"}
ALLOWED_FREQUENCIES = {"DAILY", "MONTHLY", "QUARTERLY", "ANNUAL"}


@dataclass
class TypedMacroIndicator:
    """Schema estritamente tipado para um registro histórico de indicador macroeconômico."""

    series_id: int
    indicator_code: str
    indicator_name: str
    source_institution: str
    reference_date: str        # ISO-8601: YYYY-MM-DD
    numeric_value: float
    unit: str
    frequency: str
    publication_status: str
    is_preliminary: bool
    source_page: str
    scraped_at_utc: str
    transformed_at_utc: str


@dataclass
class TransformationBatchResult:
    """Resultado consolidado da etapa de transformação e normalização (Camada Silver)."""

    batch_id: str
    transformed_at_utc: str
    input_raw_rows: int
    valid_typed_rows: int
    quarantined_rows: int
    silver_json_path: str
    silver_csv_path: str
    records: List[TypedMacroIndicator] = field(default_factory=list)
    quarantine_details: List[Dict[str, Any]] = field(default_factory=list)


class MacroDataTransformer:
    """Motor de limpeza, normalização e tipagem forte para séries macroeconômicas."""

    def __init__(self, config: Optional[ScrapingPipelineConfig] = None) -> None:
        self.config = config or ScrapingPipelineConfig()
        self.config.ensure_directories()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    @staticmethod
    def clean_text(raw: str) -> str:
        """Remove espaços excedentes, quebras de linha e entidades invisíveis."""
        cleaned = raw.replace("\xa0", " ").strip()
        return re.sub(r"\s+", " ", cleaned)

    @classmethod
    def parse_brazilian_numeric(cls, raw_value: str) -> Tuple[Optional[float], str]:
        """
        Extrai e converte valores formatados no padrão brasileiro para float.
        Exemplos:
          - '10,75% a.a. (*)' -> 10.75
          - 'R$ 5,7450 (*)'   -> 5.745
          - '1.234,56 pts'    -> 1234.56
          - 'N/D (*)'         -> None
        """
        stripped = FOOTNOTE_REGEX.sub("", raw_value)
        stripped = cls.clean_text(stripped)

        if stripped.lower() in MISSING_TOKENS:
            return None, f"Valor ausente ou não divulgado ('{raw_value.strip()}')"

        # Se possuir ponto de milhar e vírgula decimal (ex: 1.234,56)
        if "." in stripped and "," in stripped:
            normalized = stripped.replace(".", "").replace(",", ".")
        elif "," in stripped:
            normalized = stripped.replace(",", ".")
        else:
            normalized = stripped

        try:
            return round(float(normalized), 4), ""
        except ValueError:
            return None, f"Não foi possível converter '{raw_value}' (normalizado='{normalized}') para float"

    @classmethod
    def normalize_reference_date(cls, raw_date: str) -> str:
        """Converte datas 'DD/MM/YYYY' ou 'YYYY-MM-DD' para o padrão canônico ISO 'YYYY-MM-DD'."""
        cleaned = cls.clean_text(raw_date)
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        raise ValueError(f"Formato de data irreconhecível: '{raw_date}'")

    def transform_row(
        self, raw_row: Dict[str, Any], transformed_at_utc: str
    ) -> Tuple[Optional[TypedMacroIndicator], Optional[Dict[str, Any]]]:
        """
        Limpa, normaliza e aplica o schema `TypedMacroIndicator` a uma linha bruta.
        Retorna `(registro_tipado, None)` em caso de sucesso ou `(None, motivo_quarentena)`.
        """
        raw_val_str = str(raw_row.get("raw_value_str", ""))
        numeric_val, err_msg = self.parse_brazilian_numeric(raw_val_str)

        if numeric_val is None:
            return None, {
                "raw_indicator_code": self.clean_text(str(raw_row.get("raw_indicator_code", ""))),
                "raw_reference_date": self.clean_text(str(raw_row.get("raw_reference_date", ""))),
                "raw_value_str": raw_val_str.strip(),
                "reason": err_msg,
            }

        try:
            series_id = int(str(raw_row.get("series_id", "0")).strip())
            indicator_code = self.clean_text(str(raw_row["raw_indicator_code"])).upper()
            indicator_name = self.clean_text(str(raw_row["raw_indicator_name"]))
            institution = self.clean_text(str(raw_row["raw_institution"]))
            ref_date_iso = self.normalize_reference_date(str(raw_row["raw_reference_date"]))
            unit = self.clean_text(str(raw_row["raw_unit"])).upper()
            frequency = self.clean_text(str(raw_row["raw_frequency"])).upper()
            pub_status = self.clean_text(str(raw_row["raw_status"])).upper()

            if unit not in ALLOWED_UNITS:
                raise ValueError(f"Unidade '{unit}' fora do domínio permitido {sorted(ALLOWED_UNITS)}")
            if frequency not in ALLOWED_FREQUENCIES:
                raise ValueError(f"Periodicidade '{frequency}' fora do domínio {sorted(ALLOWED_FREQUENCIES)}")

            is_preliminary = pub_status != "DEFINITIVO" or "[preliminar]" in raw_val_str.lower()

            typed_record = TypedMacroIndicator(
                series_id=series_id,
                indicator_code=indicator_code,
                indicator_name=indicator_name,
                source_institution=institution,
                reference_date=ref_date_iso,
                numeric_value=numeric_val,
                unit=unit,
                frequency=frequency,
                publication_status=pub_status,
                is_preliminary=is_preliminary,
                source_page=self.clean_text(str(raw_row.get("source_page", ""))),
                scraped_at_utc=self.clean_text(str(raw_row.get("scraped_at_utc", ""))),
                transformed_at_utc=transformed_at_utc,
            )
            return typed_record, None

        except Exception as exc:
            return None, {
                "raw_row": raw_row,
                "reason": str(exc),
            }

    def run_transformation(self, bronze_file: Optional[Path] = None) -> TransformationBatchResult:
        """Lê o arquivo bruto da camada Bronze, aplica limpeza/tipagem e persiste na Silver."""
        target_bronze = bronze_file or (self.config.bronze_raw_dir / "latest_bronze_extraction.json")
        if not target_bronze.exists():
            raise FileNotFoundError(f"Arquivo de entrada Bronze não encontrado: {target_bronze}")

        with open(target_bronze, "r", encoding="utf-8") as fh:
            bronze_doc = json.load(fh)

        batch_id = str(bronze_doc.get("batch_id", "BATCH-UNKNOWN"))
        raw_rows: List[Dict[str, Any]] = bronze_doc.get("rows", [])
        now_iso = self._utc_now_iso()

        logger.info(
            "Iniciando transformação e aplicação de schema tipado | batch_id=%s | linhas_brutas=%d",
            batch_id,
            len(raw_rows),
        )

        valid_records: List[TypedMacroIndicator] = []
        quarantined: List[Dict[str, Any]] = []

        for r_row in raw_rows:
            typed_rec, quarantine_info = self.transform_row(r_row, transformed_at_utc=now_iso)
            if typed_rec is not None:
                valid_records.append(typed_rec)
            elif quarantine_info is not None:
                logger.warning(
                    "Registro movido para quarentena durante transformação | indicador=%s | data=%s | motivo=%s",
                    quarantine_info.get("raw_indicator_code"),
                    quarantine_info.get("raw_reference_date"),
                    quarantine_info.get("reason"),
                )
                quarantined.append(quarantine_info)

        # Ordena por código de indicador e data de referência
        valid_records.sort(key=lambda r: (r.indicator_code, r.reference_date))

        silver_json_path = self.config.silver_staged_dir / f"staged_macro_{batch_id}.json"
        latest_json_path = self.config.silver_staged_dir / "latest_silver_staged.json"
        latest_csv_path = self.config.silver_staged_dir / "latest_silver_staged.csv"

        payload = {
            "batch_id": batch_id,
            "transformed_at_utc": now_iso,
            "input_raw_rows": len(raw_rows),
            "valid_typed_rows": len(valid_records),
            "quarantined_rows": len(quarantined),
            "quarantine_details": quarantined,
            "records": [asdict(r) for r in valid_records],
        }

        for json_out in (silver_json_path, latest_json_path):
            with open(json_out, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)

        if valid_records:
            fieldnames = list(asdict(valid_records[0]).keys())
            with open(latest_csv_path, "w", encoding="utf-8", newline="") as csv_fh:
                writer = csv.DictWriter(csv_fh, fieldnames=fieldnames)
                writer.writeheader()
                for rec in valid_records:
                    writer.writerow(asdict(rec))

        logger.info(
            "Transformação Silver concluída | validos=%d | quarentena=%d | json=%s",
            len(valid_records),
            len(quarantined),
            silver_json_path.name,
        )

        return TransformationBatchResult(
            batch_id=batch_id,
            transformed_at_utc=now_iso,
            input_raw_rows=len(raw_rows),
            valid_typed_rows=len(valid_records),
            quarantined_rows=len(quarantined),
            silver_json_path=str(silver_json_path),
            silver_csv_path=str(latest_csv_path),
            records=valid_records,
            quarantine_details=quarantined,
        )
