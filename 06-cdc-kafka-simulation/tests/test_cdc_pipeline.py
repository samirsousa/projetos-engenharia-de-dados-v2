"""Suíte de Testes Automatizados de Engenharia de Dados para o Pipeline CDC."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cdc_connector import DebeziumCDCConnector
from src.config import PipelineConfig
from src.database import get_connection
from src.silver_consumer import SilverCDCConsumer
from src.transaction_generator import TransactionGenerator


class TestCDCPipelineEndToEnd(unittest.TestCase):
    """Valida garantias ACID, formato Debezium, idempotência LSN e reconciliação Silver."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = PipelineConfig(data_dir=Path(self.temp_dir.name))
        self.config.ensure_directories()
        self.generator = TransactionGenerator(config=self.config, seed=101)
        self.connector = DebeziumCDCConnector(config=self.config, batch_size=5)
        self.consumer = SilverCDCConsumer(config=self.config, archive_processed=False)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_01_sqlite_triggers_capture_insert_update_delete(self) -> None:
        """Verifica se as triggers SQLite gravam estados BEFORE e AFTER no _cdc_wal_log."""
        ins_res = self.generator.execute_insert()
        order_id = str(ins_res["order_id"])

        with get_connection(self.config.oltp_db_path) as conn:
            order_row = dict(
                conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            )

        self.generator.execute_update(order_row)
        self.generator.execute_delete(order_row)

        with get_connection(self.config.oltp_db_path) as conn:
            wal_rows = [
                dict(r)
                for r in conn.execute("SELECT * FROM _cdc_wal_log ORDER BY lsn ASC").fetchall()
            ]

        self.assertEqual(len(wal_rows), 3)
        self.assertEqual(wal_rows[0]["op"], "c")
        self.assertIsNone(wal_rows[0]["before_json"])
        self.assertIsNotNone(wal_rows[0]["after_json"])

        self.assertEqual(wal_rows[1]["op"], "u")
        self.assertIsNotNone(wal_rows[1]["before_json"])
        self.assertIsNotNone(wal_rows[1]["after_json"])

        self.assertEqual(wal_rows[2]["op"], "d")
        self.assertIsNotNone(wal_rows[2]["before_json"])
        self.assertIsNone(wal_rows[2]["after_json"])

    def test_02_debezium_envelope_and_silver_convergence(self) -> None:
        """Verifica se após múltiplas ondas de DML a tabela Silver converge 100% com o OLTP."""
        self.generator.run_workload(num_events=30, delay_seconds=0.0)
        emitted_files = self.connector.drain_all_pending()
        self.assertGreater(len(emitted_files), 0)

        # Valida estrutura do envelope Debezium no primeiro arquivo
        with open(emitted_files[0], "r", encoding="utf-8") as fh:
            batch_doc = json.load(fh)
        self.assertIn("batch_metadata", batch_doc)
        self.assertIn("events", batch_doc)
        first_event = batch_doc["events"][0]
        self.assertIn("schema", first_event)
        self.assertIn("payload", first_event)
        self.assertIn("source", first_event["payload"])

        # Aplica na camada Silver e confere paridade SHA-256
        metrics = self.consumer.process_all_batches()
        self.assertEqual(metrics.events_applied, 30)

        reconciliation = self.consumer.reconcile_oltp_vs_silver()
        self.assertTrue(reconciliation["is_consistent"])
        self.assertEqual(reconciliation["oltp_active_rows"], reconciliation["silver_active_rows"])
        self.assertEqual(reconciliation["oltp_sha256"], reconciliation["silver_sha256"])

        # Confere geração do relatório diário
        md_path, json_path, report_data = self.consumer.generate_daily_audit_report()
        self.assertTrue(md_path.exists())
        self.assertTrue(json_path.exists())
        self.assertEqual(report_data["daily_cdc_summary"]["total_events"], 30)

    def test_03_idempotency_on_reprocessing_same_batch(self) -> None:
        """Garante que reprocessar o mesmo arquivo JSON não duplica nem corrompe a Silver."""
        self.generator.run_workload(num_events=12, delay_seconds=0.0)
        self.connector.drain_all_pending()

        first_run = self.consumer.process_all_batches()
        self.assertEqual(first_run.events_applied, 12)

        # Segunda execução sem arquivar os arquivos: deve ignorar os lotes já processados
        second_run = self.consumer.process_all_batches()
        self.assertEqual(second_run.events_applied, 0)

        rec = self.consumer.reconcile_oltp_vs_silver()
        self.assertTrue(rec["is_consistent"])


if __name__ == "__main__":
    unittest.main()
