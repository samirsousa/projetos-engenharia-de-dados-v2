"""
Etapa 1: Geração Sintética de Dados de Assinaturas, Clientes e Movimentações de MRR.
Salva CSVs brutos em `data/raw_oltp/` e carrega o banco relacional `data/warehouse/saas_churn_analytics.db`.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RAW_OLTP_DIR, SQLITE_DB_PATH, ensure_directories
from src.subscription_generator import (
    SaaSSubscriptionSimulator,
    load_into_sqlite,
    save_raw_csvs,
)


def main() -> None:
    ensure_directories()
    simulator = SaaSSubscriptionSimulator(seed=42, start_year=2025, horizon_months=12)
    dataset = simulator.generate_dataset(base_customers_per_cohort=75)
    save_raw_csvs(dataset, output_dir=RAW_OLTP_DIR)
    counts = load_into_sqlite(dataset, db_path=SQLITE_DB_PATH)

    print("=" * 78)
    print("[ETAPA 1] GERAÇÃO DE ASSINATURAS E LEDGER DE MRR CONCLUÍDA")
    print("=" * 78)
    for table, count in counts.items():
        print(f"  -> Tabela '{table}': {count:,} registros carregados.")
    print(f"  -> SQLite Warehouse: {SQLITE_DB_PATH}")


if __name__ == "__main__":
    main()
