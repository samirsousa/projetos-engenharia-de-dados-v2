"""
Componente 3: Carregador Relacional de Séries Temporais Históricas em SQLite (`MacroWarehouseLoader`).

Responsabilidades de Engenharia:
- Modelagem dimensional (`dim_indicators` e `fact_macro_history`) em SQLite modo `WAL`.
- Carga incremental idempotente via `UPSERT` na chave composta `(indicator_code, reference_date)`.
- Controle de revisões de séries econômicas (`PRELIMINAR` -> `DEFINITIVO` com `_revision_count`).
- Views analíticas SQL (incluindo cálculo de Juro Real pela Equação de Fisher: SELIC vs IPCA).
- Geração de Relatório Analítico Macroeconômico em Markdown (`reports/macro_economic_summary.md`).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from src.config import ScrapingPipelineConfig, setup_logger

logger = setup_logger("Macro-Loader")


WAREHOUSE_DDL_SCRIPT = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- 1. Dimensão de Metadados de Séries Macroeconômicas
CREATE TABLE IF NOT EXISTS dim_indicators (
    indicator_code      TEXT PRIMARY KEY,
    series_id           INTEGER NOT NULL,
    indicator_name      TEXT NOT NULL,
    source_institution  TEXT NOT NULL,
    unit                TEXT NOT NULL,
    frequency           TEXT NOT NULL,
    updated_at_utc      TEXT NOT NULL
);

-- 2. Tabela Fato de Séries Temporais Históricas
CREATE TABLE IF NOT EXISTS fact_macro_history (
    history_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator_code          TEXT NOT NULL REFERENCES dim_indicators(indicator_code),
    reference_date          TEXT NOT NULL,
    numeric_value           REAL NOT NULL,
    publication_status      TEXT NOT NULL,
    is_preliminary          INTEGER NOT NULL CHECK (is_preliminary IN (0, 1)),
    source_page             TEXT NOT NULL,
    batch_id                TEXT NOT NULL,
    first_ingested_at_utc   TEXT NOT NULL,
    last_updated_at_utc     TEXT NOT NULL,
    revision_count          INTEGER NOT NULL DEFAULT 1,
    UNIQUE(indicator_code, reference_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_macro_date ON fact_macro_history(reference_date);
CREATE INDEX IF NOT EXISTS idx_fact_macro_code ON fact_macro_history(indicator_code);

-- 3. Tabela de Auditoria de Execuções da DAG (Airflow/Cron Simulator Metadata)
CREATE TABLE IF NOT EXISTS dag_execution_history (
    dag_run_id          TEXT PRIMARY KEY,
    dag_id              TEXT NOT NULL,
    schedule_cron       TEXT NOT NULL,
    started_at_utc      TEXT NOT NULL,
    finished_at_utc     TEXT NOT NULL,
    status              TEXT NOT NULL,
    tasks_total         INTEGER NOT NULL,
    tasks_succeeded     INTEGER NOT NULL,
    total_duration_ms   REAL NOT NULL,
    records_loaded      INTEGER NOT NULL
);

-- 4. View Analítica: Última Cotação / Divulgação Disponível por Indicador
CREATE VIEW IF NOT EXISTS vw_latest_macro_snapshot AS
SELECT
    d.indicator_code,
    d.series_id,
    d.indicator_name,
    d.source_institution,
    f.reference_date AS latest_reference_date,
    f.numeric_value AS latest_value,
    d.unit,
    f.publication_status,
    f.revision_count
FROM fact_macro_history f
INNER JOIN dim_indicators d ON d.indicator_code = f.indicator_code
WHERE f.reference_date = (
    SELECT MAX(f2.reference_date)
      FROM fact_macro_history f2
     WHERE f2.indicator_code = f.indicator_code
)
ORDER BY d.indicator_code ASC;

-- 5. View Analítica: Cálculo da Taxa de Juros Real Ex-Post (Equação de Fisher: SELIC vs IPCA 12m)
CREATE VIEW IF NOT EXISTS vw_brazil_real_interest_rate AS
SELECT
    s.reference_date,
    s.numeric_value AS selic_meta_pct_aa,
    i.numeric_value AS ipca_acum_12m_pct,
    ROUND(
        (((1.0 + (s.numeric_value / 100.0)) / (1.0 + (i.numeric_value / 100.0))) - 1.0) * 100.0,
        4
    ) AS fisher_real_interest_pct_aa,
    ROUND(s.numeric_value - i.numeric_value, 4) AS linear_spread_pct
FROM fact_macro_history s
INNER JOIN fact_macro_history i
    ON s.reference_date = i.reference_date
   AND i.indicator_code = 'IPCA_ACUM_12M'
WHERE s.indicator_code = 'SELIC_META'
ORDER BY s.reference_date ASC;
"""


@dataclass
class LoadBatchResult:
    """Métricas consolidadas da carga histórica no SQLite."""

    batch_id: str
    loaded_at_utc: str
    dimensions_upserted: int
    facts_inserted_or_updated: int
    total_historical_rows_in_db: int
    sqlite_db_path: str
    summary_report_path: str


class MacroWarehouseLoader:
    """Motor de carga histórica relacional em SQLite com suporte a UPSERT e relatórios."""

    def __init__(self, config: Optional[ScrapingPipelineConfig] = None) -> None:
        self.config = config or ScrapingPipelineConfig()
        self.config.ensure_directories()
        self._init_warehouse()

    @contextmanager
    def _get_conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.config.sqlite_db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_warehouse(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(WAREHOUSE_DDL_SCRIPT)

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def run_load(self, silver_file: Optional[Path] = None) -> LoadBatchResult:
        """Lê os registros tipados da Camada Silver e executa UPSERT histórico no SQLite."""
        target_silver = silver_file or (self.config.silver_staged_dir / "latest_silver_staged.json")
        if not target_silver.exists():
            raise FileNotFoundError(f"Arquivo Silver não encontrado para carga: {target_silver}")

        with open(target_silver, "r", encoding="utf-8") as fh:
            silver_doc = json.load(fh)

        batch_id = str(silver_doc.get("batch_id", "BATCH-UNKNOWN"))
        records: List[Dict[str, Any]] = silver_doc.get("records", [])
        now_iso = self._utc_now_iso()

        logger.info(
            "Iniciando carga histórica no SQLite Warehouse | batch_id=%s | registros=%d",
            batch_id,
            len(records),
        )

        unique_dims: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            unique_dims[str(rec["indicator_code"])] = rec

        with self._get_conn() as conn:
            # 1. Upsert na tabela dimensão `dim_indicators`
            for code, rec in unique_dims.items():
                conn.execute(
                    """
                    INSERT INTO dim_indicators (
                        indicator_code, series_id, indicator_name,
                        source_institution, unit, frequency, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(indicator_code) DO UPDATE SET
                        series_id          = excluded.series_id,
                        indicator_name     = excluded.indicator_name,
                        source_institution = excluded.source_institution,
                        unit               = excluded.unit,
                        frequency          = excluded.frequency,
                        updated_at_utc     = excluded.updated_at_utc
                    """,
                    (
                        code,
                        int(rec["series_id"]),
                        str(rec["indicator_name"]),
                        str(rec["source_institution"]),
                        str(rec["unit"]),
                        str(rec["frequency"]),
                        now_iso,
                    ),
                )

            # 2. Upsert na tabela fato histórica `fact_macro_history`
            for rec in records:
                conn.execute(
                    """
                    INSERT INTO fact_macro_history (
                        indicator_code, reference_date, numeric_value,
                        publication_status, is_preliminary, source_page,
                        batch_id, first_ingested_at_utc, last_updated_at_utc, revision_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(indicator_code, reference_date) DO UPDATE SET
                        numeric_value       = excluded.numeric_value,
                        publication_status  = excluded.publication_status,
                        is_preliminary      = excluded.is_preliminary,
                        source_page         = excluded.source_page,
                        batch_id            = excluded.batch_id,
                        last_updated_at_utc = excluded.last_updated_at_utc,
                        revision_count      = fact_macro_history.revision_count + 1
                    """,
                    (
                        str(rec["indicator_code"]),
                        str(rec["reference_date"]),
                        float(rec["numeric_value"]),
                        str(rec["publication_status"]),
                        1 if rec.get("is_preliminary") else 0,
                        str(rec["source_page"]),
                        batch_id,
                        now_iso,
                        now_iso,
                    ),
                )

            total_in_db = int(
                conn.execute("SELECT COUNT(*) AS cnt FROM fact_macro_history").fetchone()["cnt"]
            )

        summary_md_path = self.generate_macro_summary_report()

        logger.info(
            "Carga SQLite concluída | dims=%d | fatos_processados=%d | total_historico_db=%d",
            len(unique_dims),
            len(records),
            total_in_db,
        )

        return LoadBatchResult(
            batch_id=batch_id,
            loaded_at_utc=now_iso,
            dimensions_upserted=len(unique_dims),
            facts_inserted_or_updated=len(records),
            total_historical_rows_in_db=total_in_db,
            sqlite_db_path=str(self.config.sqlite_db_path),
            summary_report_path=str(summary_md_path),
        )

    def record_dag_execution(
        self,
        dag_run_id: str,
        dag_id: str,
        schedule_cron: str,
        started_at_utc: str,
        finished_at_utc: str,
        status: str,
        tasks_total: int,
        tasks_succeeded: int,
        total_duration_ms: float,
        records_loaded: int,
    ) -> None:
        """Persiste metadados da execução da DAG na tabela de observabilidade."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO dag_execution_history (
                    dag_run_id, dag_id, schedule_cron, started_at_utc, finished_at_utc,
                    status, tasks_total, tasks_succeeded, total_duration_ms, records_loaded
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dag_run_id,
                    dag_id,
                    schedule_cron,
                    started_at_utc,
                    finished_at_utc,
                    status,
                    tasks_total,
                    tasks_succeeded,
                    total_duration_ms,
                    records_loaded,
                ),
            )

    def generate_macro_summary_report(self) -> Path:
        """Gera um painel analítico em Markdown a partir das Views SQLite do Data Warehouse."""
        report_path = self.config.reports_dir / "macro_economic_summary.md"

        with self._get_conn() as conn:
            latest_snapshot = [
                dict(r) for r in conn.execute("SELECT * FROM vw_latest_macro_snapshot").fetchall()
            ]
            fisher_rates = [
                dict(r) for r in conn.execute("SELECT * FROM vw_brazil_real_interest_rate").fetchall()
            ]
            all_history = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT indicator_code, reference_date, numeric_value, publication_status, revision_count
                      FROM fact_macro_history
                     ORDER BY indicator_code ASC, reference_date ASC
                    """
                ).fetchall()
            ]

        lines = [
            "# Painel Analítico de Indicadores Macroeconômicos (SQLite Data Warehouse)",
            "",
            f"- **Gerado em (UTC):** `{self._utc_now_iso()}`",
            f"- **Banco de Dados Relacional:** `{self.config.sqlite_db_path.name}`",
            f"- **Total de Observações Históricas Armazenadas:** `{len(all_history)}`",
            "",
            "---",
            "",
            "## 1. Snapshot Mais Recente por Indicador (`vw_latest_macro_snapshot`)",
            "",
            "| Código | Série SGS/IBGE | Indicador | Instituição | Última Data | Valor | Unidade | Status | Revisões |",
            "| :--- | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
        ]

        for row in latest_snapshot:
            lines.append(
                f"| `{row['indicator_code']}` | `{row['series_id']}` | {row['indicator_name']} | "
                f"{row['source_institution']} | `{row['latest_reference_date']}` | "
                f"**{float(row['latest_value']):.4f}** | `{row['unit']}` | `{row['publication_status']}` | `{row['revision_count']}` |"
            )

        lines.extend(
            [
                "",
                "---",
                "",
                "## 2. Evolução da Taxa de Juros Real Ex-Post — Equação de Fisher (`vw_brazil_real_interest_rate`)",
                "",
                r"$$r_{\text{real}} = \left(\frac{1 + i_{\text{SELIC}}}{1 + \pi_{\text{IPCA}}} - 1\right) \times 100$$",
                "",
                "| Data de Referência | Meta SELIC (% a.a.) | IPCA Acum. 12m (%) | Juro Real Fisher (% a.a.) | Spread Linear (p.p.) |",
                "| :---: | :---: | :---: | :---: | :---: |",
            ]
        )

        for f_row in fisher_rates:
            lines.append(
                f"| `{f_row['reference_date']}` | `{float(f_row['selic_meta_pct_aa']):.2f}%` | "
                f"`{float(f_row['ipca_acum_12m_pct']):.2f}%` | "
                f"**{float(f_row['fisher_real_interest_pct_aa']):.4f}%** | "
                f"`{float(f_row['linear_spread_pct']):.2f} p.p.` |"
            )

        lines.append("")
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path
