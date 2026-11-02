"""
Etapa 3: Exportação de CSVs Agregados e Geração do Relatório Analítico de Saúde do Servidor SRE.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RAW_LOG_FILE_PATH, SQLITE_DB_PATH
from src.log_warehouse import (
    LogRelationalWarehouse,
    export_aggregated_csvs_and_sre_report,
)
from src.regex_log_parser import RegexCentralizedLogParser


def main() -> None:
    parser = RegexCentralizedLogParser()
    parsed_bundle = parser.parse_file(RAW_LOG_FILE_PATH)
    warehouse = LogRelationalWarehouse(db_path=SQLITE_DB_PATH)
    res = warehouse.load_and_aggregate(parsed_bundle)
    exported = export_aggregated_csvs_and_sre_report(res)

    print("=" * 80)
    print("[ETAPA 3] RELATÓRIO ANALÍTICO SRE & EXPORTAÇÕES CSV GERADOS")
    print("=" * 80)
    for k, v in exported.items():
        print(f"  -> {k:<24}: {v}")


if __name__ == "__main__":
    main()
