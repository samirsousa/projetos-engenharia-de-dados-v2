"""
Etapa 2: Execução das Consultas SQL Analíticas Avançadas (Churn, Cohort Analysis & LTV).
Materializa as tabelas `mart_*` no banco SQLite e exibe os indicadores executivos no console.
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
from src.config import ANALYTICAL_SQL_PATH, SQLITE_DB_PATH


def main() -> None:
    marts = execute_analytical_sql(db_path=SQLITE_DB_PATH, sql_path=ANALYTICAL_SQL_PATH)
    summary = compute_executive_summary_and_impact(marts, db_path=SQLITE_DB_PATH)

    print("=" * 78)
    print("[ETAPA 2] CONSULTAS SQL ANALÍTICAS (CHURN, COHORT & LTV) EXECUTADAS")
    print("=" * 78)
    for mart_name, rows in marts.items():
        print(f"  -> Mart SQL '{mart_name}': {len(rows)} linhas materializadas.")
    print("-" * 78)
    print(f"  * Clientes Ativos no Fechamento ({summary['latest_snapshot_month']}): {summary['ending_active_customers']}")
    print(f"  * Ending MRR: R$ {summary['ending_mrr_brl']:,.2f} | Ending ARR: R$ {summary['ending_arr_brl']:,.2f}")
    print(f"  * Logo Churn Médio Mensal: {summary['avg_logo_churn_pct']:.2f}%")
    print(f"  * Net MRR Churn Médio: {summary['avg_net_mrr_churn_pct']:.2f}% | NRR Médio: {summary['avg_nrr_pct']:.2f}%")
    print(f"  * LTV Médio Ponderado: R$ {summary['weighted_ltv_brl']:,.2f} | CAC Médio: R$ {summary['weighted_cac_brl']:,.2f} (LTV:CAC = {summary['global_ltv_cac_ratio']:.2f}x)")


if __name__ == "__main__":
    main()
