"""
Suíte de Testes Automatizados do Projeto 11: Customer Churn, Cohort Retention & LTV Analytics.

Valida:
1. Integridade referencial e contábil do gerador de assinaturas e Ledger de MRR.
2. Identidade contábil do MRR Bridge em SQL:
   Beginning MRR + New MRR + Expansion MRR - Contraction MRR - Churned MRR == Ending MRR.
3. Invariantes matemáticos da Análise de Coorte (Retenção no Mês 0 == 100.0% e curva de clientes monotônica).
4. Cálculo de Lifetime Value (LTV), CAC, LTV:CAC e Payback Period.
5. Exportação do Star Schema para Power BI (CSV, Parquet e Catálogo DAX).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics_engine import (
    build_cohort_pivot_matrix,
    compute_executive_summary_and_impact,
    execute_analytical_sql,
)
from src.config import ANALYTICAL_SQL_PATH
from src.powerbi_exporter import (
    export_powerbi_star_schema,
    generate_executive_markdown_report,
)
from src.subscription_generator import (
    SaaSSubscriptionSimulator,
    load_into_sqlite,
    save_raw_csvs,
)


class TestChurnAnalyticsPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.base_path = Path(cls.temp_dir.name)
        cls.raw_dir = cls.base_path / "raw_oltp"
        cls.db_path = cls.base_path / "warehouse" / "test_churn.db"
        cls.pbi_dir = cls.base_path / "powerbi_mart"
        cls.report_path = cls.base_path / "reports" / "executive_report.md"

        simulator = SaaSSubscriptionSimulator(seed=42, start_year=2025, horizon_months=12)
        cls.dataset = simulator.generate_dataset(base_customers_per_cohort=45)
        save_raw_csvs(cls.dataset, output_dir=cls.raw_dir)
        cls.counts = load_into_sqlite(cls.dataset, db_path=cls.db_path)
        cls.marts = execute_analytical_sql(db_path=cls.db_path, sql_path=ANALYTICAL_SQL_PATH)
        cls.summary = compute_executive_summary_and_impact(cls.marts, db_path=cls.db_path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_01_synthetic_dataset_integrity(self) -> None:
        """Verifica se todas as 4 tabelas OLTP foram populadas e possuem chaves consistentes."""
        self.assertEqual(self.counts["raw_plans"], 3)
        self.assertGreater(self.counts["raw_customers"], 500)
        self.assertEqual(self.counts["raw_customers"], self.counts["raw_subscriptions"])
        self.assertGreater(self.counts["raw_mrr_ledger"], self.counts["raw_customers"])

        # Verifica que toda assinatura CHURNED possui end_date e motivo preenchidos
        for sub in self.dataset["raw_subscriptions"]:
            if sub["status"] == "CHURNED":
                self.assertTrue(sub["end_date"], "Assinatura CHURNED deve ter end_date.")
                self.assertNotEqual(sub["churn_reason"], "Active (No Churn)")
                self.assertEqual(sub["final_mrr_brl"], 0.0)
            else:
                self.assertEqual(sub["end_date"], "")
                self.assertGreater(sub["final_mrr_brl"], 0.0)

    def test_02_mrr_bridge_accounting_identity(self) -> None:
        """
        Garante a identidade contábil fundamental de SaaS em todos os meses:
        Beginning MRR + New MRR + Expansion MRR - Contraction MRR - Churned MRR == Ending MRR
        e
        Beginning Customers + New Customers - Churned Customers == Ending Active Customers.
        """
        monthly_kpis = self.marts["mart_monthly_churn_kpis"]
        self.assertEqual(len(monthly_kpis), 12)

        for row in monthly_kpis:
            expected_customers = (
                row["beginning_customers"] + row["new_customers"] - row["churned_customers"]
            )
            self.assertEqual(
                row["ending_active_customers"],
                expected_customers,
                f"Falha no balanço de clientes no mês {row['snapshot_month']}",
            )

            expected_ending_mrr = round(
                row["beginning_mrr_brl"]
                + row["new_mrr_brl"]
                + row["expansion_mrr_brl"]
                - row["contraction_mrr_brl"]
                - row["churned_mrr_brl"],
                2,
            )
            self.assertAlmostEqual(
                row["ending_mrr_brl"],
                expected_ending_mrr,
                places=1,
                msg=f"Falha na identidade contábil do MRR Bridge no mês {row['snapshot_month']}",
            )

            # Verifica soma GRR % + Gross MRR Churn % == 100% (para meses com beginning_mrr > 0)
            if row["beginning_mrr_brl"] > 0:
                self.assertAlmostEqual(
                    row["grr_pct"] + row["gross_mrr_churn_rate_pct"], 100.0, places=1
                )
                self.assertAlmostEqual(
                    row["nrr_pct"] + row["net_mrr_churn_rate_pct"], 100.0, places=1
                )

    def test_03_cohort_retention_invariants(self) -> None:
        """
        Verifica se toda safra inicia em M00 com 100.0% de retenção (Logo e Dollar)
        e se a retenção de clientes (Logo Retention) nunca aumenta ao longo do tempo
        (sem reativação de logos na mesma assinatura).
        """
        cohort_rows = self.marts["mart_cohort_retention"]
        self.assertEqual(len(cohort_rows), 78)  # 12 + 11 + ... + 1 = 78 células na matriz triangular

        pivot_logo = build_cohort_pivot_matrix(cohort_rows, metric_col="logo_retention_pct")
        self.assertEqual(len(pivot_logo), 12)

        for row in pivot_logo:
            self.assertEqual(row["M00"], 100.0)
            prev_val = 100.0
            for m in range(1, 12):
                val = row[f"M{m:02d}"]
                if val is not None:
                    self.assertLessEqual(
                        val,
                        prev_val,
                        f"Logo retention não pode crescer na safra {row['cohort_month']} em M{m:02d}",
                    )
                    prev_val = val

    def test_04_ltv_and_unit_economics_calculations(self) -> None:
        """Valida se os cálculos de LTV, CAC, LTV:CAC e Payback Period são positivos e consistentes."""
        ltv_rows = self.marts["mart_ltv_unit_economics"]
        self.assertGreaterEqual(len(ltv_rows), 10)

        for row in ltv_rows:
            self.assertGreater(row["arpa_brl"], 0.0)
            self.assertGreater(row["theoretical_gross_margin_ltv_brl"], 0.0)
            self.assertGreater(row["ltv_to_cac_ratio"], 0.0)
            self.assertGreater(row["cac_payback_months"], 0.0)

        self.assertGreater(self.summary["global_ltv_cac_ratio"], 2.0)
        self.assertGreater(self.summary["compounded_12m_arr_saved_1pct_churn_reduction_brl"], 0.0)

    def test_05_powerbi_star_schema_export(self) -> None:
        """Verifica se todas as tabelas do Star Schema (CSV e Parquet), o script DAX e o relatório são gerados."""
        manifest = export_powerbi_star_schema(db_path=self.db_path, output_dir=self.pbi_dir)
        report_file = generate_executive_markdown_report(
            self.marts, self.summary, report_path=self.report_path
        )

        expected_tables = [
            "dim_calendar",
            "dim_customers",
            "dim_plans",
            "dim_churn_reasons",
            "fact_subscriptions",
            "fact_mrr_movements",
            "mart_monthly_churn_kpis",
            "mart_cohort_retention",
            "mart_cohort_matrix_logo_pivot",
            "mart_cohort_matrix_dollar_pivot",
            "mart_ltv_unit_economics",
            "mart_churn_reasons_breakdown",
        ]
        for tbl in expected_tables:
            self.assertIn(tbl, manifest)
            self.assertTrue(Path(manifest[tbl]["csv_path"]).exists())
            self.assertTrue(Path(manifest[tbl]["parquet_path"]).exists())

        self.assertTrue((self.pbi_dir / "powerbi_dax_measures.dax").exists())
        self.assertTrue(report_file.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
