"""Suíte de Testes Unitários e de Integração da Feature Store para Machine Learning."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import FeatureStoreConfig
from src.feature_engineering import FeatureEngineeringPipeline
from src.feature_store import LocalFeatureStore
from src.oltp_seeder import OLTP_ECOMMERCE_DDL, EcommerceOLTPSeeder


class TestFeatureStoreML(unittest.TestCase):
    """Valida cálculos RFM, Ticket Móvel, Sazonalidade, Anti-Leakage Point-in-Time e Camada Gold."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = FeatureStoreConfig(base_dir=Path(self.temp_dir.name))
        self.config.ensure_directories()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_01_point_in_time_anti_leakage_and_exact_formulas(self) -> None:
        """
        Garante que pedidos ocorridos após `as_of_timestamp` NÃO vazem (Data Leakage)
        para as features históricas e sejam usados exclusivamente nas variáveis target.
        """
        conn = sqlite3.connect(str(self.config.oltp_db_path))
        try:
            conn.executescript(OLTP_ECOMMERCE_DDL)
            conn.execute(
                "INSERT INTO customers VALUES ('CUST-TEST', 'Cliente Teste', 'SP', 'ORGANIC_SEARCH', '2026-01-01')"
            )
            # 4 pedidos ANTES do cutoff (2026-10-01T23:59:59Z) e 1 pedido DEPOIS do cutoff (2026-10-15)
            orders = [
                ("ORD-1", "CUST-TEST", "2026-07-01T10:00:00Z", "CatA", 1, 100.0, 0.0, 100.0, "PIX", "COMPLETED"),
                ("ORD-2", "CUST-TEST", "2026-08-01T10:00:00Z", "CatA", 1, 200.0, 0.0, 200.0, "PIX", "COMPLETED"),
                ("ORD-3", "CUST-TEST", "2026-09-01T22:00:00Z", "CatB", 2, 300.0, 0.0, 300.0, "CREDIT_CARD", "COMPLETED"),
                ("ORD-4", "CUST-TEST", "2026-09-21T22:00:00Z", "CatB", 2, 400.0, 0.0, 400.0, "PIX", "COMPLETED"),
                # Pedido no futuro pós-cutoff (não pode entrar no RFM nem no Ticket Médio!)
                ("ORD-5", "CUST-TEST", "2026-10-15T14:00:00Z", "CatC", 5, 9999.0, 0.0, 9999.0, "PIX", "COMPLETED"),
            ]
            conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", orders)
            conn.commit()
        finally:
            conn.close()

        fe = FeatureEngineeringPipeline(config=self.config)
        vectors = fe.compute_customer_features(
            as_of_timestamp="2026-10-01T23:59:59Z", label_horizon_days=30
        )
        self.assertEqual(len(vectors), 1)
        vec = vectors[0]

        # Verifica RFM sem vazamento do pedido ORD-5 (9999.0)
        self.assertEqual(vec.rfm_frequency_total, 4)
        self.assertEqual(vec.rfm_monetary_total, 1000.0)  # 100 + 200 + 300 + 400
        self.assertEqual(vec.aov_lifetime, 250.0)         # 1000 / 4

        # Verifica Ticket Médio Móvel das últimas 3 compras: (200 + 300 + 400) / 3 = 300.0
        self.assertEqual(vec.rolling_aov_last_3, 300.0)
        self.assertEqual(vec.aov_momentum_ratio, 1.2)     # 300 / 250 = 1.2

        # Verifica Entropia de Shannon: 2 CatA e 2 CatB -> distribuição 50%/50% -> Entropia = 1.0 bit
        self.assertEqual(vec.category_shannon_entropy, 1.0)

        # Verifica que o pedido futuro ORD-5 entrou apenas nos targets supervisionados
        self.assertEqual(vec.target_churn_30d, 0)
        self.assertEqual(vec.target_next_30d_spend, 9999.0)

    def test_02_end_to_end_gold_materialization_and_online_offline_serving(self) -> None:
        """Valida pipeline completo: OLTP -> Engenharia de Features -> Gold Parquet/SQLite -> Serving."""
        seeder = EcommerceOLTPSeeder(config=self.config, seed=99)
        seeder.seed_database(num_customers=24)

        fe = FeatureEngineeringPipeline(config=self.config)
        vectors = fe.compute_customer_features()
        self.assertEqual(len(vectors), 24)

        store = LocalFeatureStore(config=self.config)
        registry = store.materialize_gold_layer(vectors)
        self.assertEqual(registry["total_entities"], 24)

        self.assertTrue(self.config.offline_parquet_path.exists())
        self.assertTrue(self.config.offline_scaled_parquet_path.exists())
        self.assertTrue(self.config.offline_csv_path.exists())
        self.assertTrue(self.config.online_db_path.exists())
        self.assertTrue(self.config.registry_json_path.exists())

        # Testa Online Feature Store (baixa latência)
        online_res = store.get_online_features(
            ["CUST-0001", "CUST-0002"],
            feature_names=["rfm_recency_days", "rolling_aov_last_3", "rfm_segment"],
        )
        self.assertEqual(len(online_res), 2)
        self.assertIn("rolling_aov_last_3", online_res[0])

        # Testa Offline Feature Store (dataset bruto e Z-score scaled)
        offline_raw = store.get_historical_training_dataset(scaled=False)
        offline_scaled = store.get_historical_training_dataset(scaled=True)
        self.assertEqual(len(offline_raw), 24)
        self.assertEqual(len(offline_scaled), 24)
        self.assertIn("rfm_monetary_total_zscore", offline_scaled[0])

        # Verifica que a média de uma feature padronizada por Z-Score é ~0.0
        mean_z = sum(float(r["rfm_monetary_total_zscore"]) for r in offline_scaled) / len(offline_scaled)
        self.assertAlmostEqual(mean_z, 0.0, places=4)

        # Gera relatório analítico
        report_md = store.generate_feature_store_report()
        self.assertTrue(report_md.exists())


if __name__ == "__main__":
    unittest.main()
