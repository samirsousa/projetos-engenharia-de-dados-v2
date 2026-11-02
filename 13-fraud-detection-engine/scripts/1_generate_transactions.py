"""
Etapa 1: Geração Sintética de Clientes e Transações Financeiras com Tipologias de Fraude.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RAW_TX_DIR, SQLITE_DB_PATH, ensure_directories
from src.transaction_generator import (
    FinancialTransactionSimulator,
    save_raw_transactions_and_load_db,
)


def main() -> None:
    ensure_directories()
    sim = FinancialTransactionSimulator(seed=42)
    dataset = sim.generate_dataset(num_customers=100)
    counts = save_raw_transactions_and_load_db(dataset, raw_dir=RAW_TX_DIR, db_path=SQLITE_DB_PATH)

    print("=" * 80)
    print("[ETAPA 1] BASE DE TRANSAÇÕES FINANCEIRAS GERADA E CARREGADA NO SQLITE")
    print("=" * 80)
    for tbl, cnt in counts.items():
        print(f"  -> Tabela '{tbl:<20}': {cnt:>6,} registros")
    print(f"  -> SQLite Warehouse: {SQLITE_DB_PATH}")


if __name__ == "__main__":
    main()
