"""
Suíte de Testes Automatizados do Projeto 13: Sistema de Alerta de Anomalias em Transações Financeiras.

Valida:
1. Propriedade Anti-Masking do estimador estatístico de baseline (Média, Desvio Padrão, Mediana, MAD).
2. Persistência e integridade da tabela `suspect_transactions` no banco SQLite.
3. Eficácia de detecção das tipologias de fraude via Z-Score (Precision, Recall e F1-Score >= 90%).
4. Exportação dos relatórios executivos em CSV, CSV Excel PT-BR, Planilha Excel Multi-Abas (.xls) e Markdown.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fraud_engine import (
    StatisticalFraudDetectionEngine,
    compute_robust_distribution_stats,
)
from src.report_exporter import (
    export_executive_csv_and_excel,
    generate_markdown_executive_report,
)
from src.transaction_generator import (
    FinancialTransactionSimulator,
    save_raw_transactions_and_load_db,
)


class TestFraudDetectionEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.base_path = Path(cls.temp_dir.name)
        cls.raw_dir = cls.base_path / "raw_transactions"
        cls.db_path = cls.base_path / "warehouse" / "test_fraud.db"
        cls.exports_dir = cls.base_path / "exports"
        cls.report_path = cls.base_path / "reports" / "executive_report.md"

        sim = FinancialTransactionSimulator(seed=42)
        cls.dataset = sim.generate_dataset(num_customers=60)
        cls.raw_counts = save_raw_transactions_and_load_db(
            cls.dataset, raw_dir=cls.raw_dir, db_path=cls.db_path
        )

        engine = StatisticalFraudDetectionEngine(db_path=cls.db_path)
        cls.results = engine.run_detection()
        cls.exported = export_executive_csv_and_excel(
            cls.results, exports_dir=cls.exports_dir
        )
        cls.report_file = generate_markdown_executive_report(
            cls.results, report_path=cls.report_path
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_01_robust_baseline_anti_masking_math(self) -> None:
        """
        Verifica se um outlier extremo (ex: fraude de R$ 9.500 em uma conta com gastos
        normais de R$ 100 a R$ 160) não contamina a média e o desvio padrão de baseline.
        """
        normal_tx = [110.0, 125.0, 130.0, 140.0, 135.0, 120.0, 145.0, 150.0, 128.0, 132.0]
        contaminated_tx = normal_tx + [9500.0]

        stats_clean = compute_robust_distribution_stats(normal_tx)
        stats_contam = compute_robust_distribution_stats(contaminated_tx)

        # O desvio bruto explode com o outlier (> 2800), mas o baseline_std_brl permanece intacto (~12.4)
        self.assertGreater(stats_contam["raw_std_brl"], 2500.0)
        self.assertAlmostEqual(
            stats_clean["baseline_mean_brl"], stats_contam["baseline_mean_brl"], places=2
        )
        self.assertAlmostEqual(
            stats_clean["baseline_std_brl"], stats_contam["baseline_std_brl"], places=2
        )

    def test_02_suspect_transactions_table_in_sqlite(self) -> None:
        """Garante que a tabela `suspect_transactions` foi criada no SQLite e contém apenas anomalias."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM suspect_transactions")
            rows = [dict(r) for r in cur.fetchall()]
            self.assertGreater(len(rows), 20)
            self.assertEqual(len(rows), len(self.results["suspect_transactions"]))

            for r in rows:
                self.assertEqual(r["is_suspect"], 1)
                self.assertTrue(
                    r["user_z_score"] >= 3.0 or r["composite_risk_score"] >= 50.0,
                    f"Registro {r['transaction_id']} em suspect_transactions sem critério válido.",
                )
        finally:
            conn.close()

    def test_03_statistical_detection_precision_and_recall(self) -> None:
        """Valida a precisão, cobertura (Recall) e F1-Score do motor sobre as fraudes injetadas."""
        m = self.results["metrics"]
        self.assertGreaterEqual(m["precision_pct"], 90.0)
        self.assertGreaterEqual(m["recall_pct"], 90.0)
        self.assertGreaterEqual(m["f1_score_pct"], 90.0)
        self.assertLessEqual(m["false_positive_rate_pct"], 1.5)
        self.assertGreater(m["prevented_fraud_loss_brl"], 0.0)

    def test_04_executive_csv_and_excel_exports(self) -> None:
        """Verifica se os arquivos CSV, CSV PT-BR, Planilha Excel Multi-Abas (.xls) e Markdown existem."""
        for key, file_path in self.exported.items():
            p = Path(file_path)
            self.assertTrue(p.exists(), f"Arquivo exportado ausente: {key} -> {p}")
            self.assertGreater(p.stat().st_size, 100)

        xls_content = Path(self.exported["excel_workbook_xls"]).read_text(encoding="utf-8")
        self.assertIn("4_Suspect_Transactions", xls_content)
        self.assertTrue(self.report_file.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
