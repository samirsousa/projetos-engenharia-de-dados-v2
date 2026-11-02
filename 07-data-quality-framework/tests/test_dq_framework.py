"""Suíte de Testes Unitários e de Integração do Data Quality & Observability Framework."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DQConfig
from src.connectors import CSVDataConnector, ParquetDataConnector, SQLiteDataConnector, TabularDataset
from src.contracts import ColumnContract, DataContract, ExpectedDataType, RuleSeverity
from src.observability import ObservabilityReporter
from src.sample_factory import (
    build_csv_transactions_sample,
    build_parquet_telemetry_sample,
    build_sqlite_customers_samples,
)
from src.validators import DataQualityEngine


class TestDataQualityFramework(unittest.TestCase):
    """Valida regras de nulidade, unicidade, range, tipos de dados, conectores e alertas."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = DQConfig(base_dir=Path(self.temp_dir.name))
        self.config.ensure_directories()
        self.engine = DataQualityEngine()
        self.reporter = ObservabilityReporter(config=self.config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_01_core_validators_null_unique_range_and_type(self) -> None:
        """Verifica isoladamente as 4 dimensões: nulidade, unicidade, range e tipo."""
        contract = DataContract(
            contract_id="DC-UNIT-001",
            dataset_name="Unit_Test_Dataset",
            source_format="MEMORY",
            owner_team="Data-Reliability-Team",
            primary_key_column="id",
            columns=[
                ColumnContract(
                    name="id",
                    expected_type=ExpectedDataType.INT,
                    nullable=False,
                    unique=True,
                    is_primary_key=True,
                ),
                ColumnContract(
                    name="score",
                    expected_type=ExpectedDataType.FLOAT,
                    nullable=False,
                    min_value=0.0,
                    max_value=10.0,
                ),
                ColumnContract(
                    name="status",
                    expected_type=ExpectedDataType.STRING,
                    nullable=False,
                    allowed_values=["ACTIVE", "INACTIVE"],
                ),
            ],
        )

        dataset = TabularDataset(
            source_name="memory_table",
            source_format="MEMORY",
            columns=["id", "score", "status"],
            rows=[
                {"id": "1", "score": "8.5", "status": "ACTIVE"},          # Saudável
                {"id": "1", "score": "7.0", "status": "ACTIVE"},          # Violação UNIQUENESS (id=1)
                {"id": "", "score": "5.0", "status": "INACTIVE"},         # Violação NULLABILITY (id="")
                {"id": "4", "score": "15.2", "status": "ACTIVE"},         # Violação RANGE_CHECK (score > 10)
                {"id": "5", "score": "NAO_NUMERICO", "status": "ACTIVE"}, # Violação DATA_TYPE (score)
                {"id": "6", "score": "4.0", "status": "PENDING"},         # Violação RANGE_CHECK (domínio)
            ],
        )

        report = self.engine.evaluate(dataset, contract)
        self.assertFalse(report.contract_passed)
        self.assertEqual(report.total_rows, 6)
        self.assertEqual(report.healthy_rows_count, 1)
        self.assertEqual(report.corrupted_rows_count, 5)

        categories = report.violations_by_category
        self.assertEqual(categories.get("UNIQUENESS"), 1)
        self.assertEqual(categories.get("NULLABILITY"), 1)
        self.assertEqual(categories.get("DATA_TYPE"), 1)
        self.assertEqual(categories.get("RANGE_CHECK"), 2)

    def test_02_csv_connector_and_contract_violation_logs(self) -> None:
        """Valida leitura de arquivo CSV, detecção de anomalias e geração de log/alerta."""
        csv_path, contract = build_csv_transactions_sample(self.config)
        dataset = CSVDataConnector(csv_path).load()
        report = self.engine.evaluate(dataset, contract)

        self.assertFalse(report.contract_passed)
        self.assertEqual(report.total_rows, 10)
        self.assertEqual(report.healthy_rows_count, 5)
        self.assertEqual(report.corrupted_rows_count, 5)

        json_log, central_log = self.reporter.write_anomaly_logs(report)
        alert_file = self.reporter.dispatch_alert_if_needed(report, print_to_console=False)

        self.assertTrue(json_log.exists())
        self.assertTrue(central_log.exists())
        self.assertIsNotNone(alert_file)
        assert alert_file is not None
        self.assertTrue(alert_file.exists())

        with open(json_log, "r", encoding="utf-8") as fh:
            logged_data = json.load(fh)
        self.assertEqual(logged_data["event_type"], "DATA_CONTRACT_VIOLATION")
        self.assertGreaterEqual(len(logged_data["anomalies"]), 5)

    def test_03_parquet_connector_validation(self) -> None:
        """Valida leitura e inspeção de arquivo Apache Parquet (.parquet)."""
        parquet_path, contract = build_parquet_telemetry_sample(self.config)
        dataset = ParquetDataConnector(parquet_path).load()
        report = self.engine.evaluate(dataset, contract)

        self.assertFalse(report.contract_passed)
        self.assertEqual(report.total_rows, 8)
        self.assertEqual(report.healthy_rows_count, 4)
        self.assertEqual(report.corrupted_rows_count, 4)

    def test_04_sqlite_dirty_vs_clean_tables(self) -> None:
        """Valida tabelas SQLite com anomalias (Silver) e 100% conformes (Gold)."""
        db_path, silver_contract, gold_contract = build_sqlite_customers_samples(self.config)

        silver_ds = SQLiteDataConnector(db_path, "customers_silver").load()
        silver_report = self.engine.evaluate(silver_ds, silver_contract)
        self.assertFalse(silver_report.contract_passed)
        self.assertGreater(len(silver_report.anomalies), 0)

        gold_ds = SQLiteDataConnector(db_path, "customers_gold_clean").load()
        gold_report = self.engine.evaluate(gold_ds, gold_contract)
        self.assertTrue(gold_report.contract_passed)
        self.assertEqual(gold_report.data_quality_score, 100.0)
        self.assertEqual(len(gold_report.anomalies), 0)

        # Tabela Gold limpa não deve disparar alerta de incidente
        gold_alert = self.reporter.dispatch_alert_if_needed(gold_report, print_to_console=False)
        self.assertIsNone(gold_alert)


if __name__ == "__main__":
    unittest.main()
