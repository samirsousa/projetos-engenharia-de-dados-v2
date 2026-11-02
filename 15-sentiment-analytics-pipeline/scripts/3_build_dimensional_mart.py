"""
Etapa 3: Consolidação em Tabelas Dimensionais (Star Schema), NPS por Categoria e Exportação para Dashboard.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DASHBOARD_MART_DIR, RAW_REVIEWS_JSON_PATH, SQLITE_DB_PATH
from src.dimensional_builder import (
    DimensionalSentimentBuilder,
    export_dashboard_marts_and_report,
)
from src.sentiment_engine import SentimentAnalyticsProcessor


def main() -> None:
    processor = SentimentAnalyticsProcessor()
    enriched = processor.process_json_file(RAW_REVIEWS_JSON_PATH)

    builder = DimensionalSentimentBuilder(db_path=SQLITE_DB_PATH)
    build_res = builder.build_and_persist(enriched)
    exported = export_dashboard_marts_and_report(build_res, mart_dir=DASHBOARD_MART_DIR)

    print("=" * 80)
    print("[ETAPA 3] STAR SCHEMA DIMENSIONAL, NPS E EXPORTAÇÃO PARA DASHBOARD CONCLUÍDOS")
    print("=" * 80)
    for tbl, cnt in build_res["table_counts"].items():
        print(f"  -> Tabela '{tbl:<38}': {cnt:>5,} linhas")
    print(f"  -> Relatório Executivo: {exported['executive_markdown_report']}")


if __name__ == "__main__":
    main()
