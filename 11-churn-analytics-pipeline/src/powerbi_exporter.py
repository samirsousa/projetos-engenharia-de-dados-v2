"""
Exportador de Modelagem Dimensional (Star Schema) para Power BI e Gerador de Relatório Executivo.

Constrói e exporta:
1. Tabelas Dimensão (`dim_calendar`, `dim_customers`, `dim_plans`, `dim_churn_reasons`)
2. Tabelas Fato (`fact_subscriptions`, `fact_mrr_movements`)
3. Tabelas Mart Pré-Agregadas (`mart_monthly_churn_kpis`, `mart_cohort_retention`,
   `mart_cohort_matrix_logo_pivot`, `mart_cohort_matrix_dollar_pivot`,
   `mart_ltv_unit_economics`, `mart_churn_reasons_breakdown`)
4. Catálogo de Medidas DAX (`powerbi_dax_measures.dax`) prontas para copiar e colar no Power BI Desktop.
5. Relatório Executivo Markdown (`reports/churn_retention_executive_report.md`).
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Dict, List, Any

import pandas as pd

from src.analytics_engine import build_cohort_pivot_matrix
from src.config import POWERBI_MART_DIR, REPORTS_DIR, SQLITE_DB_PATH

MONTH_NAMES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

MONTH_ABBR_PT = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


def _build_dim_calendar(start_year: int = 2025, num_months: int = 12) -> List[Dict[str, Any]]:
    """Gera a dimensão de calendário mensal/diário para relacionamento no Power BI."""
    rows: List[Dict[str, Any]] = []
    year, month = start_year, 1
    for idx in range(num_months):
        ym = f"{year:04d}-{month:02d}"
        quarter = ((month - 1) // 3) + 1
        rows.append(
            {
                "date_key": f"{ym}-01",
                "snapshot_month": ym,
                "year": year,
                "quarter": f"Q{quarter}",
                "year_quarter": f"{year}-Q{quarter}",
                "month_number": month,
                "month_name_pt": MONTH_NAMES_PT[month],
                "month_abbr_pt": f"{MONTH_ABBR_PT[month]}/{str(year)[2:]}",
                "month_sort_order": year * 100 + month,
                "is_quarter_end": 1 if month in (3, 6, 9, 12) else 0,
                "month_index_seq": idx + 1,
            }
        )
        month += 1
        if month > 12:
            month = 1
            year += 1
    return rows


def export_powerbi_star_schema(
    db_path: Path = SQLITE_DB_PATH,
    output_dir: Path = POWERBI_MART_DIR,
) -> Dict[str, Dict[str, Any]]:
    """
    Lê as tabelas do SQLite Warehouse, constrói o Star Schema completo para Power BI
    e exporta cada tabela em CSV (UTF-8) e Apache Parquet.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        cur = conn.cursor()

        # 1. Dimensões
        dim_calendar = _build_dim_calendar(start_year=2025, num_months=12)

        cur.execute("SELECT * FROM raw_customers ORDER BY customer_id")
        dim_customers = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT * FROM raw_plans ORDER BY tier_level")
        dim_plans = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT DISTINCT
                churn_type,
                churn_reason,
                CASE WHEN churn_type = 'Involuntary' THEN 1 ELSE 0 END AS is_preventable_by_dunning
            FROM raw_subscriptions
            ORDER BY churn_type, churn_reason
            """
        )
        dim_churn_reasons = [
            {"churn_reason_key": f"CR-{i+1:02d}", **dict(r)}
            for i, r in enumerate(cur.fetchall())
        ]

        # 2. Tabelas Fato
        cur.execute("SELECT * FROM raw_subscriptions ORDER BY subscription_id")
        fact_subscriptions = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT
                l.*,
                l.snapshot_month || '-01' AS date_key
            FROM raw_mrr_ledger l
            ORDER BY l.ledger_id
            """
        )
        fact_mrr_movements = [dict(r) for r in cur.fetchall()]

        # 3. Tabelas Mart Analíticas
        cur.execute("SELECT * FROM mart_monthly_churn_kpis ORDER BY snapshot_month")
        mart_monthly_churn_kpis = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT * FROM mart_cohort_retention ORDER BY cohort_month, months_since_signup")
        mart_cohort_retention = [dict(r) for r in cur.fetchall()]

        mart_cohort_matrix_logo_pivot = build_cohort_pivot_matrix(
            mart_cohort_retention, metric_col="logo_retention_pct"
        )
        mart_cohort_matrix_dollar_pivot = build_cohort_pivot_matrix(
            mart_cohort_retention, metric_col="dollar_retention_pct"
        )

        cur.execute("SELECT * FROM mart_ltv_unit_economics ORDER BY ltv_to_cac_ratio DESC")
        mart_ltv_unit_economics = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT * FROM mart_churn_reasons_breakdown ORDER BY lost_mrr_brl DESC")
        mart_churn_reasons_breakdown = [dict(r) for r in cur.fetchall()]

        tables_to_export = {
            "dim_calendar": dim_calendar,
            "dim_customers": dim_customers,
            "dim_plans": dim_plans,
            "dim_churn_reasons": dim_churn_reasons,
            "fact_subscriptions": fact_subscriptions,
            "fact_mrr_movements": fact_mrr_movements,
            "mart_monthly_churn_kpis": mart_monthly_churn_kpis,
            "mart_cohort_retention": mart_cohort_retention,
            "mart_cohort_matrix_logo_pivot": mart_cohort_matrix_logo_pivot,
            "mart_cohort_matrix_dollar_pivot": mart_cohort_matrix_dollar_pivot,
            "mart_ltv_unit_economics": mart_ltv_unit_economics,
            "mart_churn_reasons_breakdown": mart_churn_reasons_breakdown,
        }

        manifest: Dict[str, Dict[str, Any]] = {}
        for table_name, rows in tables_to_export.items():
            if not rows:
                continue
            csv_path = output_dir / f"{table_name}.csv"
            parquet_path = output_dir / f"{table_name}.parquet"

            fieldnames = list(rows[0].keys())
            with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            df = pd.DataFrame(rows)
            df.to_parquet(parquet_path, index=False)

            manifest[table_name] = {
                "row_count": len(rows),
                "columns": fieldnames,
                "csv_path": str(csv_path),
                "parquet_path": str(parquet_path),
            }

        # Exporta também o catálogo oficial de medidas DAX para Power BI
        dax_path = output_dir / "powerbi_dax_measures.dax"
        dax_path.write_text(_generate_dax_catalog(), encoding="utf-8")
        manifest["powerbi_dax_measures"] = {
            "row_count": 14,
            "columns": ["DAX Measure Script"],
            "dax_path": str(dax_path),
        }

        return manifest
    finally:
        conn.close()


def _generate_dax_catalog() -> str:
    """Retorna script DAX documentado com todas as medidas oficiais para o Power BI Desktop."""
    return """// =============================================================================
// CATÁLOGO OFICIAL DE MEDIDAS DAX - SAAS CHURN, COHORT & LTV ANALYTICS
// Tabela recomendada para hospedar as medidas no Power BI: [_Measures]
// =============================================================================

// 1. Clientes Ativos no Período
Active Customers = 
CALCULATE(
    DISTINCTCOUNT(fact_mrr_movements[customer_id]),
    fact_mrr_movements[active_flag] = 1
)

// 2. Clientes Cancelados no Mês (Churned Logos)
Churned Customers = 
CALCULATE(
    DISTINCTCOUNT(fact_mrr_movements[customer_id]),
    fact_mrr_movements[movement_type] = "CHURNED"
)

// 3. Clientes Ativos no Mês Anterior (Beginning Customers)
Beginning Customers = 
CALCULATE(
    [Active Customers],
    DATEADD(dim_calendar[date_key], -1, MONTH)
)

// 4. Taxa de Logo Churn Mensal (%)
Logo Churn Rate % = 
DIVIDE([Churned Customers], [Beginning Customers], 0)

// 5. MRR Final (Ending MRR R$)
Ending MRR (BRL) = 
CALCULATE(
    SUM(fact_mrr_movements[current_mrr_brl]),
    fact_mrr_movements[active_flag] = 1
)

// 6. ARR (Annual Recurring Revenue R$)
Ending ARR (BRL) = [Ending MRR (BRL)] * 12

// 7. MRR Inicial (Beginning MRR R$)
Beginning MRR (BRL) = 
CALCULATE(
    [Ending MRR (BRL)],
    DATEADD(dim_calendar[date_key], -1, MONTH)
)

// 8. MRR Perdido por Cancelamento (Churned MRR R$)
Churned MRR (BRL) = 
CALCULATE(
    SUM(fact_mrr_movements[previous_mrr_brl]),
    fact_mrr_movements[movement_type] = "CHURNED"
)

// 9. MRR de Contração / Downgrade (Contraction MRR R$)
Contraction MRR (BRL) = 
ABS(
    CALCULATE(
        SUM(fact_mrr_movements[mrr_delta_brl]),
        fact_mrr_movements[movement_type] = "CONTRACTION"
    )
)

// 10. MRR de Expansão / Upsell (Expansion MRR R$)
Expansion MRR (BRL) = 
CALCULATE(
    SUM(fact_mrr_movements[mrr_delta_brl]),
    fact_mrr_movements[movement_type] = "EXPANSION"
)

// 11. Gross MRR Churn Rate (%)
Gross MRR Churn % = 
DIVIDE(
    [Churned MRR (BRL)] + [Contraction MRR (BRL)],
    [Beginning MRR (BRL)],
    0
)

// 12. Net MRR Churn Rate (%) - Valores negativos indicam Net Negative Churn!
Net MRR Churn % = 
DIVIDE(
    [Churned MRR (BRL)] + [Contraction MRR (BRL)] - [Expansion MRR (BRL)],
    [Beginning MRR (BRL)],
    0
)

// 13. Net Dollar Retention - NRR / NDR (%)
Net Revenue Retention (NRR %) = 1 - [Net MRR Churn %]

// 14. Retenção de Coorte (Logo Retention % para Matriz cohort_month x period_label)
Cohort Logo Retention % = 
VAR CurrentActive = [Active Customers]
VAR InitialCohortSize = 
    CALCULATE(
        DISTINCTCOUNT(fact_mrr_movements[customer_id]),
        fact_mrr_movements[months_since_signup] = 0,
        ALLEXCEPT(fact_mrr_movements, fact_mrr_movements[cohort_month])
    )
RETURN
    DIVIDE(CurrentActive, InitialCohortSize, BLANK())

// 15. ARPA (Ticket Médio Mensal por Conta Ativa)
ARPA (BRL) = DIVIDE([Ending MRR (BRL)], [Active Customers], 0)

// 16. LTV Ajustado por Margem Bruta (R$)
Customer LTV (BRL) = 
VAR GrossMarginPct = 0.82
VAR MonthlyGrossProfitPerCust = [ARPA (BRL)] * GrossMarginPct
VAR ChurnRate = MAX([Logo Churn Rate %], 0.01)
RETURN
    DIVIDE(MonthlyGrossProfitPerCust, ChurnRate, 0)
"""


def generate_executive_markdown_report(
    marts: Dict[str, List[Dict[str, Any]]],
    summary: Dict[str, Any],
    report_path: Path = REPORTS_DIR / "churn_retention_executive_report.md",
) -> Path:
    """Gera o relatório executivo detalhado em Markdown com tabelas de KPIs, Coorte e LTV."""
    report_path.parent.mkdir(parents=True, exist_ok=True)

    monthly_kpis = marts["mart_monthly_churn_kpis"]
    cohort_rows = marts["mart_cohort_retention"]
    ltv_rows = marts["mart_ltv_unit_economics"]
    reasons_rows = marts["mart_churn_reasons_breakdown"]
    logo_pivot = build_cohort_pivot_matrix(cohort_rows, metric_col="logo_retention_pct")

    lines: List[str] = [
        "# Relatório Executivo: Customer Churn, Cohort Retention & LTV Analytics",
        "",
        f"**Mês de Fechamento (Snapshot):** `{summary['latest_snapshot_month']}`",
        "",
        "## 1. Sumário Executivo de Indicadores SaaS (North Star KPIs)",
        "",
        "| Indicador (KPI) | Valor Consolidado | Benchmark SaaS B2B | Status |",
        "| :--- | ---: | :--- | :--- |",
        f"| **Clientes Ativos no Fechamento** | `{summary['ending_active_customers']}` | - | Base Ativa |",
        f"| **MRR de Fechamento (Ending MRR)** | `R$ {summary['ending_mrr_brl']:,.2f}` | - | Receita Recorrente Mensal |",
        f"| **ARR de Fechamento (Ending ARR)** | `R$ {summary['ending_arr_brl']:,.2f}` | - | Run-rate Anualizado |",
        f"| **ARPA (Ticket Médio Mensal)** | `R$ {summary['latest_arpa_brl']:,.2f}` | - | Receita Média por Conta |",
        f"| **Logo Churn Mensal Médio** | `{summary['avg_logo_churn_pct']:.2f}%` | `< 3.50%` (Blended) | Monitoramento de Onboarding |",
        f"| **Gross MRR Churn Médio** | `{summary['avg_gross_mrr_churn_pct']:.2f}%` | `< 2.50%` | Perda Bruta de Receita |",
        f"| **Net MRR Churn Médio** | `{summary['avg_net_mrr_churn_pct']:.2f}%` | `< 0.00%` (Ideal) | Compensado por Expansão |",
        f"| **GRR Médio (Gross Revenue Retention)** | `{summary['avg_grr_pct']:.2f}%` | `> 90% a 97%` | Retenção Bruta Mensal |",
        f"| **NRR / NDR Médio (Net Dollar Retention)** | `{summary['avg_nrr_pct']:.2f}%` | `> 100.0%` | Eficiência de Upsell/Cross-sell |",
        f"| **LTV Médio Ponderado (Margem Bruta)** | `R$ {summary['weighted_ltv_brl']:,.2f}` | `> 3x CAC` | Valor no Ciclo de Vida |",
        f"| **CAC Médio Ponderado** | `R$ {summary['weighted_cac_brl']:,.2f}` | - | Custo de Aquisição |",
        f"| **Razão Global LTV : CAC** | `{summary['global_ltv_cac_ratio']:.2f}x` | `>= 3.00x` | Unit Economics Saudável |",
        "",
        "---",
        "",
        "## 2. Evolução Mensal de MRR Bridge & Taxas de Churn",
        "",
        "| Mês | Base Inicial | Novos | Churn | Base Final | Beginning MRR (R$) | New MRR (R$) | Expansion (R$) | Churned MRR (R$) | Ending MRR (R$) | Logo Churn % | Net MRR Churn % | NRR % |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for r in monthly_kpis:
        lines.append(
            f"| `{r['snapshot_month']}` | {r['beginning_customers']} | +{r['new_customers']} | "
            f"-{r['churned_customers']} | **{r['ending_active_customers']}** | "
            f"{r['beginning_mrr_brl']:,.2f} | +{r['new_mrr_brl']:,.2f} | "
            f"+{r['expansion_mrr_brl']:,.2f} | -{r['churned_mrr_brl']:,.2f} | "
            f"**{r['ending_mrr_brl']:,.2f}** | `{r['logo_churn_rate_pct']:.2f}%` | "
            f"`{r['net_mrr_churn_rate_pct']:.2f}%` | `{r['nrr_pct']:.2f}%` |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Matriz de Coorte de Retenção de Clientes (Logo Cohort Retention %)",
            "",
            "| Safra (Cohort) | Clientes M00 | M00 | M01 | M02 | M03 | M04 | M05 | M06 | M07 | M08 | M09 | M10 | M11 |",
            "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for row in logo_pivot:
        cells = []
        for m in range(12):
            val = row.get(f"M{m:02d}")
            cells.append(f"{val:.1f}%" if val is not None else "-")
        lines.append(
            f"| `{row['cohort_month']}` | {row['cohort_initial_customers']} | "
            + " | ".join(cells)
            + " |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Lifetime Value (LTV) & Unit Economics por Segmento e Canal",
            "",
            "| Segmento | Canal de Aquisição | Clientes | ARPA (R$) | Churn Mensal % | Lifetime (Meses) | LTV Margem Bruta (R$) | CAC (R$) | LTV:CAC | Payback (Meses) | Diagnóstico |",
            "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
        ]
    )

    for r in ltv_rows:
        lines.append(
            f"| **{r['segment']}** | {r['acquisition_channel']} | {r['total_customers_acquired']} | "
            f"{r['arpa_brl']:,.2f} | `{r['monthly_churn_rate_pct']:.2f}%` | "
            f"{r['expected_lifetime_months']:.1f} | **{r['theoretical_gross_margin_ltv_brl']:,.2f}** | "
            f"{r['avg_cac_brl']:,.2f} | **`{r['ltv_to_cac_ratio']:.2f}x`** | "
            f"{r['cac_payback_months']:.1f} | {r['unit_economics_health']} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 5. Diagnóstico de Motivos de Cancelamento & Impacto Financeiro",
            "",
            "| Tipo de Churn | Motivo Declarado / Raiz | Segmento | Contas Perdidas | MRR Perdido (R$) | ARR Perdido (R$) | Tenure Médio (Meses) |",
            "| :--- | :--- | :--- | ---: | ---: | ---: | ---: |",
        ]
    )

    for r in reasons_rows[:12]:
        lines.append(
            f"| `{r['churn_type']}` | {r['churn_reason']} | {r['segment']} | "
            f"{r['churned_subscriptions']} | {r['lost_mrr_brl']:,.2f} | "
            f"**{r['lost_arr_brl']:,.2f}** | {r['avg_tenure_before_churn_months']:.1f} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 6. Simulação Executiva de Impacto Financeiro da Retenção",
            "",
            f"1. **Redução de 1.0 p.p. no Churn Mensal (Alavanca de Customer Success & Onboarding):**",
            f"   - Economia Composta de MRR em 12 meses: **`R$ {summary['compounded_12m_mrr_saved_1pct_churn_reduction_brl']:,.2f} / mês`**",
            f"   - Aumento Direto de ARR (Receita Anual Recorrente): **`R$ {summary['compounded_12m_arr_saved_1pct_churn_reduction_brl']:,.2f} / ano`**",
            f"   - Criação de Valor no Valuation da Empresa (Múltiplo 6.0x ARR): **`R$ {summary['enterprise_value_impact_6x_arr_brl']:,.2f}`**",
            f"2. **Automação de Dunning & Recuperação de Churn Involuntário (Cartão Expirado/Falha de Pagamento):**",
            f"   - ARR Total Perdido por Falha de Cobrança Involuntária: `R$ {summary['involuntary_arr_lost_brl']:,.2f}`",
            f"   - ARR Recuperável Imediato (taxa de recuperação de 65% via Smart Retries & Pix/Boleto Fallback): **`R$ {summary['dunning_recovered_arr_brl']:,.2f} / ano`**",
            "",
        ]
    )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
