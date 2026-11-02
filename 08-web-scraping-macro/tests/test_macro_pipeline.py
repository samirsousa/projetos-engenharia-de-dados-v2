"""Suíte de Testes Automatizados para o Pipeline de Web Scraping Macroeconômico e Orquestrador DAG."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ScrapingPipelineConfig
from src.dag_orchestrator import DAG, DAGCycleError, PythonTask, TaskState, build_macro_scraping_dag
from src.extractor import MacroWebExtractor, RobotsTxtDisallowedError, TransientScrapeError
from src.loader import MacroWarehouseLoader
from src.portal_simulator import ROBOTS_TXT_CONTENT
from src.transformer import MacroDataTransformer


class TestMacroScrapingPipeline(unittest.TestCase):
    """Testa Extração (Retry/Robots.txt), Transformação Tipada, Carga SQLite e Motor DAG."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = ScrapingPipelineConfig(base_dir=Path(self.temp_dir.name))
        self.config.ensure_directories()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_01_robots_txt_compliance_and_retry_backoff(self) -> None:
        """Verifica bloqueio ético por robots.txt e recuperação de falhas transitórias HTTP 503."""
        extractor = MacroWebExtractor(config=self.config, simulate_transient_failures=2)

        # Caminho permitido deve passar
        self.assertTrue(extractor.verify_robots_txt(ROBOTS_TXT_CONTENT, "/boletim_focus_sgs.html"))

        # Caminho proibido em robots.txt deve lançar RobotsTxtDisallowedError imediatamente
        with self.assertRaises(RobotsTxtDisallowedError):
            extractor.verify_robots_txt(ROBOTS_TXT_CONTENT, "/admin/config.html")

        # Executa extração com 2 falhas transitórias injetadas (max_retries=3 -> deve recuperar)
        res = extractor.run_extraction(batch_id="TEST-BATCH-01")
        self.assertEqual(res.total_retry_attempts, 2)
        self.assertEqual(res.total_raw_rows, 26)
        self.assertTrue(Path(res.bronze_file_path).exists())

        # Se falhas transitórias excederem max_retries (ex: 5 > 3), deve falhar com TransientScrapeError
        failing_extractor = MacroWebExtractor(config=self.config, simulate_transient_failures=5)
        with self.assertRaises(TransientScrapeError):
            failing_extractor.run_extraction(batch_id="TEST-BATCH-FAIL")

    def test_02_transformer_cleaning_and_brazilian_number_parsing(self) -> None:
        """Verifica limpeza de notas de rodapé, conversão decimal BR, datas ISO e quarentena."""
        val1, err1 = MacroDataTransformer.parse_brazilian_numeric("10,75% a.a. (*)")
        self.assertEqual(val1, 10.75)
        self.assertEqual(err1, "")

        val2, err2 = MacroDataTransformer.parse_brazilian_numeric("R$ 5,7450 [1]")
        self.assertEqual(val2, 5.745)
        self.assertEqual(err2, "")

        val_nd, err_nd = MacroDataTransformer.parse_brazilian_numeric("N/D (*)")
        self.assertIsNone(val_nd)
        self.assertIn("ausente", err_nd)

        iso_dt = MacroDataTransformer.normalize_reference_date("01/11/2026")
        self.assertEqual(iso_dt, "2026-11-01")

    def test_03_dag_cycle_detection_and_upstream_failed_propagation(self) -> None:
        """Valida Algoritmo de Kahn para detecção de ciclos e propagação de UPSTREAM_FAILED."""
        cyclic_dag = DAG(dag_id="cyclic_test_dag")
        t_a = cyclic_dag.add_task(PythonTask("task_a", lambda ctx: "A"))
        t_b = cyclic_dag.add_task(PythonTask("task_b", lambda ctx: "B"))
        t_a >> t_b
        t_b >> t_a  # Ciclo A -> B -> A

        with self.assertRaises(DAGCycleError):
            cyclic_dag.topological_sort()

        # Testa propagação UPSTREAM_FAILED quando tarefa intermediária falha
        fail_dag = DAG(dag_id="upstream_fail_dag")
        n1 = fail_dag.add_task(PythonTask("n1_ok", lambda ctx: "OK", retries=0))

        def _raise_err(ctx: object) -> None:
            raise RuntimeError("Falha simulada na task n2")

        n2 = fail_dag.add_task(PythonTask("n2_fail", _raise_err, retries=1, retry_delay_sec=0.01))
        n3 = fail_dag.add_task(PythonTask("n3_downstream", lambda ctx: "NEVER_RUNS", retries=0))
        n1 >> n2 >> n3

        run_res = fail_dag.execute()
        self.assertEqual(run_res.overall_status, "FAILED")
        states = {t.task_id: t.state for t in run_res.task_telemetries}
        self.assertEqual(states["n1_ok"], TaskState.SUCCESS)
        self.assertEqual(states["n2_fail"], TaskState.FAILED)
        self.assertEqual(states["n3_downstream"], TaskState.UPSTREAM_FAILED)

    def test_04_end_to_end_dag_and_sqlite_idempotent_upsert(self) -> None:
        """Executa a DAG completa duas vezes e valida idempotência UPSERT e revisão no SQLite."""
        dag = build_macro_scraping_dag(config=self.config, simulate_transient_failures=1)
        first_run = dag.execute(run_id="RUN-01")
        self.assertEqual(first_run.overall_status, "SUCCESS")

        # 26 linhas brutas - 1 linha 'N/D' em quarentena = 25 registros históricos válidos
        self.assertEqual(
            first_run.xcom_snapshot["t3_clean_and_type_schema"]["valid_typed_rows"], 25
        )
        self.assertEqual(
            first_run.xcom_snapshot["t3_clean_and_type_schema"]["quarantined_rows"], 1
        )
        self.assertEqual(
            first_run.xcom_snapshot["t5_load_sqlite_warehouse"]["total_db_rows"], 25
        )

        # Segunda execução sobre a mesma janela histórica: não deve duplicar linhas (continua 25)
        # e deve incrementar revision_count para 2
        second_run = dag.execute(run_id="RUN-02")
        self.assertEqual(second_run.overall_status, "SUCCESS")
        self.assertEqual(
            second_run.xcom_snapshot["t5_load_sqlite_warehouse"]["total_db_rows"], 25
        )

        conn = sqlite3.connect(str(self.config.sqlite_db_path))
        try:
            rev_cnt = conn.execute(
                "SELECT MAX(revision_count) FROM fact_macro_history"
            ).fetchone()[0]
            self.assertEqual(rev_cnt, 2)

            fisher_rows = conn.execute(
                "SELECT COUNT(*) FROM vw_brazil_real_interest_rate"
            ).fetchone()[0]
            self.assertEqual(fisher_rows, 4)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
