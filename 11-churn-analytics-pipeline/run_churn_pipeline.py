"""
Orquestrador End-to-End do Projeto 11: Customer Churn & Retention Analytics Pipeline.

Executa sequencialmente:
1. Simulação e carga OLTP de clientes, assinaturas e ledger mensal de MRR (`raw_*`).
2. Consultas SQL analíticas avançadas (`mart_monthly_churn_kpis`, `mart_cohort_retention`,
   `mart_ltv_unit_economics`, `mart_churn_reasons_breakdown`).
3. Estruturação do Star Schema para Power BI (CSV + Parquet + Catálogo DAX) e geração
   do Relatório Executivo Markdown (`reports/churn_retention_executive_report.md`).
"""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from src.analytics_engine import (
    build_cohort_pivot_matrix,
    compute_executive_summary_and_impact,
    execute_analytical_sql,
)
from src.config import (
    ANALYTICAL_SQL_PATH,
    DATA_DIR,
    POWERBI_MART_DIR,
    RAW_OLTP_DIR,
    REPORTS_DIR,
    SQLITE_DB_PATH,
    ensure_directories,
)
from src.powerbi_exporter import (
    export_powerbi_star_schema,
    generate_executive_markdown_report,
)
from src.subscription_generator import (
    SaaSSubscriptionSimulator,
    load_into_sqlite,
    save_raw_csvs,
)


def run_pipeline(clean: bool = False, seed: int = 42, base_cohort_size: int = 75) -> dict:
    start_ts = time.perf_counter()

    if clean:
        for d in (DATA_DIR, REPORTS_DIR):
            if d.exists():
                shutil.rmtree(d)

    ensure_directories()

    print("=" * 84)
    print("  PROJETO 11: CUSTOMER CHURN, COHORT RETENTION & LTV ANALYTICS PIPELINE")
    print("=" * 84)

    # 1. Geração Sintética de Assinaturas e Ledger de MRR
    print("\n[1/3] Gerando base sintética de assinaturas SaaS e histórico mensal de MRR...")
    simulator = SaaSSubscriptionSimulator(seed=seed, start_year=2025, horizon_months=12)
    dataset = simulator.generate_dataset(base_customers_per_cohort=base_cohort_size)
    save_raw_csvs(dataset, output_dir=RAW_OLTP_DIR)
    table_counts = load_into_sqlite(dataset, db_path=SQLITE_DB_PATH)
    for tbl, cnt in table_counts.items():
        print(f"      - {tbl:<22}: {cnt:>6,} registros")

    # 2. Execução das Queries SQL Analíticas Avançadas
    print("\n[2/3] Executando consultas SQL analíticas (Monthly Churn, Cohort Matrix & LTV)...")
    marts = execute_analytical_sql(db_path=SQLITE_DB_PATH, sql_path=ANALYTICAL_SQL_PATH)
    summary = compute_executive_summary_and_impact(marts, db_path=SQLITE_DB_PATH)
    for mart_name, rows in marts.items():
        print(f"      - {mart_name:<30}: {len(rows):>4} linhas analíticas")

    # 3. Exportação do Star Schema para Power BI & Relatório Executivo
    print("\n[3/3] Exportando Star Schema para Power BI (CSV + Parquet + DAX) e Relatório...")
    manifest = export_powerbi_star_schema(db_path=SQLITE_DB_PATH, output_dir=POWERBI_MART_DIR)
    report_path = generate_executive_markdown_report(marts, summary)
    print(f"      - Tabelas/Artefatos Power BI exportados em: {POWERBI_MART_DIR}")
    print(f"      - Relatório Executivo gerado em           : {report_path}")

    elapsed = time.perf_counter() - start_ts

    print("\n" + "=" * 84)
    print("  RESUMO EXECUTIVO DOS INDICADORES DE RETENÇÃO & UNIT ECONOMICS (SAAS B2B)")
    print("=" * 84)
    print(f"  * Mês de Fechamento Analisado        : {summary['latest_snapshot_month']}")
    print(f"  * Total de Clientes Adquiridos (Ano) : {summary['total_customers_acquired']:,}")
    print(f"  * Total de Cancelamentos (Logo Churn): {summary['total_customers_churned']:,}")
    print(f"  * Clientes Ativos no Fechamento      : {summary['ending_active_customers']:,}")
    print(f"  * Ending MRR (Receita Mensal)        : R$ {summary['ending_mrr_brl']:,.2f}")
    print(f"  * Ending ARR (Receita Anualizada)    : R$ {summary['ending_arr_brl']:,.2f}")
    print(f"  * ARPA (Ticket Médio Mensal)         : R$ {summary['latest_arpa_brl']:,.2f}")
    print("-" * 84)
    print(f"  * Taxa Média de Logo Churn Mensal    : {summary['avg_logo_churn_pct']:.2f}%")
    print(f"  * Taxa Média de Gross MRR Churn      : {summary['avg_gross_mrr_churn_pct']:.2f}%")
    print(f"  * Taxa Média de Net MRR Churn        : {summary['avg_net_mrr_churn_pct']:.2f}%")
    print(f"  * Retenção Bruta Média (GRR)         : {summary['avg_grr_pct']:.2f}%")
    print(f"  * Retenção Líquida Média (NRR / NDR) : {summary['avg_nrr_pct']:.2f}%")
    print("-" * 84)
    print(f"  * LTV Médio Ponderado (Margem Bruta) : R$ {summary['weighted_ltv_brl']:,.2f}")
    print(f"  * CAC Médio Ponderado                : R$ {summary['weighted_cac_brl']:,.2f}")
    print(f"  * Razão Global LTV : CAC             : {summary['global_ltv_cac_ratio']:.2f}x")
    print("-" * 84)
    print("  IMPACTO FINANCEIRO DE ALAVANCAS DE RETENÇÃO:")
    print(
        f"  1) Redução de 1.0 p.p. no Churn Mensal -> +R$ {summary['compounded_12m_arr_saved_1pct_churn_reduction_brl']:,.2f} em ARR "
        f"(+R$ {summary['enterprise_value_impact_6x_arr_brl']:,.2f} em Valuation @ 6x ARR)"
    )
    print(
        f"  2) Automação de Dunning (65% recup.)   -> +R$ {summary['dunning_recovered_arr_brl']:,.2f} em ARR salvo de cartões recusados"
    )
    print("=" * 84)
    print(f"Pipeline concluído com sucesso em {elapsed:.2f}s.\n")

    return {
        "table_counts": table_counts,
        "summary": summary,
        "manifest": manifest,
        "report_path": str(report_path),
        "cohort_logo_pivot": build_cohort_pivot_matrix(
            marts["mart_cohort_retention"], metric_col="logo_retention_pct"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa o pipeline completo de Customer Churn, Cohort Analysis & LTV."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove artefatos anteriores antes de executar o pipeline.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed aleatória para reprodutibilidade determinística (padrão: 42).",
    )
    args = parser.parse_args()
    run_pipeline(clean=args.clean, seed=args.seed)


if __name__ == "__main__":
    main()
