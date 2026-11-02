"""
Etapa 3: Estruturação e Exportação do Star Schema (Dimensões, Fatos, Marts e DAX) para Power BI.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics_engine import (
    compute_executive_summary_and_impact,
    execute_analytical_sql,
)
from src.config import POWERBI_MART_DIR, REPORTS_DIR, SQLITE_DB_PATH
from src.powerbi_exporter import (
    export_powerbi_star_schema,
    generate_executive_markdown_report,
)


def main() -> None:
    marts = execute_analytical_sql(db_path=SQLITE_DB_PATH)
    summary = compute_executive_summary_and_impact(marts, db_path=SQLITE_DB_PATH)
    manifest = export_powerbi_star_schema(db_path=SQLITE_DB_PATH, output_dir=POWERBI_MART_DIR)
    report_path = generate_executive_markdown_report(marts, summary)

    print("=" * 78)
    print("[ETAPA 3] EXPORTAÇÃO STAR SCHEMA PARA POWER BI & RELATÓRIO EXECUTIVO")
    print("=" * 78)
    for table_name, meta in manifest.items():
        print(f"  -> Artefato '{table_name}': {meta['row_count']} linhas exportadas.")
    print(f"  -> Diretório Power BI Mart: {POWERBI_MART_DIR}")
    print(f"  -> Relatório Executivo Markdown: {report_path}")


if __name__ == "__main__":
    main()
