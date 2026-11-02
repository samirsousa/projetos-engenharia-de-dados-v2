"""
Motor de Execução Analítica SQL (Churn, Cohort Analysis & LTV).

Executa o script `sql/analytical_queries.sql` no SQLite Data Warehouse,
constrói matrizes pivotadas de retenção por coorte (M00..M11) e calcula
simulações de impacto financeiro de retenção para tomada de decisão executiva.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Any

from src.config import ANALYTICAL_SQL_PATH, SQLITE_DB_PATH


def execute_analytical_sql(
    db_path: Path = SQLITE_DB_PATH,
    sql_path: Path = ANALYTICAL_SQL_PATH,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Executa todas as queries analíticas do arquivo `analytical_queries.sql`
    e retorna os registros das tabelas `mart_*` materializadas.
    """
    sql_script = sql_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.executescript(sql_script)
        conn.commit()

        marts = [
            "mart_monthly_churn_kpis",
            "mart_cohort_retention",
            "mart_ltv_unit_economics",
            "mart_churn_reasons_breakdown",
        ]
        results: Dict[str, List[Dict[str, Any]]] = {}
        for mart in marts:
            cur.execute(f"SELECT * FROM {mart}")
            results[mart] = [dict(row) for row in cur.fetchall()]

        return results
    finally:
        conn.close()


def build_cohort_pivot_matrix(
    cohort_rows: List[Dict[str, Any]],
    metric_col: str = "logo_retention_pct",
    max_months: int = 11,
) -> List[Dict[str, Any]]:
    """
    Transforma a tabela longa `mart_cohort_retention` em uma matriz triangular
    pivotada (linhas = `cohort_month`, colunas = `M00`, `M01`, ..., `M11`),
    ideal para visualização direta e exportação executiva.
    """
    by_cohort: Dict[str, Dict[str, Any]] = {}
    for row in cohort_rows:
        c_month = row["cohort_month"]
        if c_month not in by_cohort:
            by_cohort[c_month] = {
                "cohort_month": c_month,
                "cohort_initial_customers": row["cohort_initial_customers"],
                "cohort_initial_mrr_brl": row["cohort_initial_mrr_brl"],
            }
            for m in range(max_months + 1):
                by_cohort[c_month][f"M{m:02d}"] = None

        m_idx = int(row["months_since_signup"])
        if 0 <= m_idx <= max_months:
            by_cohort[c_month][f"M{m_idx:02d}"] = row[metric_col]

    return [by_cohort[k] for k in sorted(by_cohort.keys())]


def compute_executive_summary_and_impact(
    marts: Dict[str, List[Dict[str, Any]]],
    db_path: Path = SQLITE_DB_PATH,
) -> Dict[str, Any]:
    """
    Calcula o sumário executivo consolidado de Churn, Retenção, LTV:CAC e
    simula o impacto financeiro no ARR e Enterprise Valuation de alavancas de retenção.
    """
    monthly_kpis = marts["mart_monthly_churn_kpis"]
    ltv_rows = marts["mart_ltv_unit_economics"]
    reasons_rows = marts["mart_churn_reasons_breakdown"]

    # Considera meses onde já havia base inicial (snapshot_month > primeiro mês)
    active_months = [r for r in monthly_kpis if r["beginning_customers"] > 0]
    latest_month = monthly_kpis[-1]

    avg_logo_churn_pct = round(
        sum(r["logo_churn_rate_pct"] for r in active_months) / len(active_months), 2
    )
    avg_gross_mrr_churn_pct = round(
        sum(r["gross_mrr_churn_rate_pct"] for r in active_months) / len(active_months), 2
    )
    avg_net_mrr_churn_pct = round(
        sum(r["net_mrr_churn_rate_pct"] for r in active_months) / len(active_months), 2
    )
    avg_grr_pct = round(
        sum(r["grr_pct"] for r in active_months) / len(active_months), 2
    )
    avg_nrr_pct = round(
        sum(r["nrr_pct"] for r in active_months) / len(active_months), 2
    )

    total_customers_acquired = sum(r["new_customers"] for r in monthly_kpis)
    total_customers_churned = sum(r["churned_customers"] for r in monthly_kpis)
    total_churned_mrr_brl = round(sum(r["churned_mrr_brl"] for r in monthly_kpis), 2)
    total_expansion_mrr_brl = round(sum(r["expansion_mrr_brl"] for r in monthly_kpis), 2)

    # Ponderado de LTV e CAC global
    total_cust_ltv = sum(r["total_customers_acquired"] for r in ltv_rows)
    weighted_ltv_brl = round(
        sum(r["theoretical_gross_margin_ltv_brl"] * r["total_customers_acquired"] for r in ltv_rows)
        / max(1, total_cust_ltv),
        2,
    )
    weighted_cac_brl = round(
        sum(r["avg_cac_brl"] * r["total_customers_acquired"] for r in ltv_rows)
        / max(1, total_cust_ltv),
        2,
    )
    global_ltv_cac_ratio = round(weighted_ltv_brl / max(1.0, weighted_cac_brl), 2)

    # Churn Involuntário (Cartão Expirado / Falha de Cobrança)
    involuntary_mrr_lost = round(
        sum(r["lost_mrr_brl"] for r in reasons_rows if r["churn_type"] == "Involuntary"), 2
    )
    involuntary_arr_lost = round(involuntary_mrr_lost * 12.0, 2)

    # Simulação de Impacto Financeiro (Alavancas de Retenção):
    # Alavanca 1: Reduzir Logo/MRR Churn em 1.0 ponto percentual (100 bps) ao mês sobre o MRR final atual
    ending_mrr_brl = latest_month["ending_mrr_brl"]
    ending_arr_brl = latest_month["ending_arr_brl"]

    # Efeito composto de reter +1.0% de MRR ao mês durante 12 meses
    compounded_12m_mrr_saved = round(ending_mrr_brl * ((1.01 ** 12) - 1.0), 2)
    compounded_12m_arr_saved = round(compounded_12m_mrr_saved * 12.0, 2)
    # Múltiplo de Valuation SaaS conservador de 6.0x ARR
    enterprise_value_impact_brl = round(compounded_12m_arr_saved * 6.0, 2)

    # Alavanca 2: Recuperar 65% do Churn Involuntário com Dunning Inteligente & Retentativa Automática
    dunning_recovered_arr_brl = round(involuntary_arr_lost * 0.65, 2)

    return {
        "latest_snapshot_month": latest_month["snapshot_month"],
        "total_customers_acquired": total_customers_acquired,
        "total_customers_churned": total_customers_churned,
        "ending_active_customers": latest_month["ending_active_customers"],
        "ending_mrr_brl": ending_mrr_brl,
        "ending_arr_brl": ending_arr_brl,
        "latest_arpa_brl": latest_month["arpa_brl"],
        "avg_logo_churn_pct": avg_logo_churn_pct,
        "avg_gross_mrr_churn_pct": avg_gross_mrr_churn_pct,
        "avg_net_mrr_churn_pct": avg_net_mrr_churn_pct,
        "avg_grr_pct": avg_grr_pct,
        "avg_nrr_pct": avg_nrr_pct,
        "total_churned_mrr_brl": total_churned_mrr_brl,
        "total_expansion_mrr_brl": total_expansion_mrr_brl,
        "weighted_ltv_brl": weighted_ltv_brl,
        "weighted_cac_brl": weighted_cac_brl,
        "global_ltv_cac_ratio": global_ltv_cac_ratio,
        "involuntary_mrr_lost_brl": involuntary_mrr_lost,
        "involuntary_arr_lost_brl": involuntary_arr_lost,
        "dunning_recovered_arr_brl": dunning_recovered_arr_brl,
        "compounded_12m_mrr_saved_1pct_churn_reduction_brl": compounded_12m_mrr_saved,
        "compounded_12m_arr_saved_1pct_churn_reduction_brl": compounded_12m_arr_saved,
        "enterprise_value_impact_6x_arr_brl": enterprise_value_impact_brl,
    }
