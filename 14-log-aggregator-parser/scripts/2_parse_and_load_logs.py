"""
Etapa 2: Extração via Expressões Regulares Avançadas (Regex) e Carga Agregada no SQLite.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RAW_LOG_FILE_PATH, SQLITE_DB_PATH
from src.log_warehouse import LogRelationalWarehouse
from src.regex_log_parser import RegexCentralizedLogParser


def main() -> None:
    parser = RegexCentralizedLogParser()
    parsed_bundle = parser.parse_file(RAW_LOG_FILE_PATH)

    warehouse = LogRelationalWarehouse(db_path=SQLITE_DB_PATH)
    res = warehouse.load_and_aggregate(parsed_bundle)

    print("=" * 80)
    print("[ETAPA 2] PARSER REGEX E CARGA RELACIONAL SQLITE CONCLUÍDOS")
    print("=" * 80)
    for tbl, cnt in res["table_counts"].items():
        print(f"  -> Tabela SQLite '{tbl:<32}': {cnt:>5,} linhas")


if __name__ == "__main__":
    main()
