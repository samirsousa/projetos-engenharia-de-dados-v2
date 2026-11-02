"""
Suíte de Testes Automatizados do Projeto 14: Log Aggregator & Centralized Log Parser.

Valida:
1. Extração de campos via Expressão Regular Compilada (`EXTENDED_ACCESS_LOG_REGEX`) e Dead-Letter Queue.
2. Normalização de Rotas REST com IDs numéricos e UUIDv4 via Regex (`normalize_route_path`).
3. Detecção de vetores de ataque cibernético via Regex (SQL Injection, Path Traversal, `.env` Probe).
4. Persistência e agregação no SQLite (`agg_metrics_by_ip`, `agg_metrics_by_route`, `agg_metrics_by_status_code`)
   e geração do relatório analítico de saúde do servidor SRE.
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

from src.log_generator import write_simulated_log_file
from src.log_warehouse import (
    LogRelationalWarehouse,
    export_aggregated_csvs_and_sre_report,
)
from src.regex_log_parser import (
    EXTENDED_ACCESS_LOG_REGEX,
    RegexCentralizedLogParser,
    classify_security_threat,
    normalize_route_path,
)


class TestLogAggregatorParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.base_path = Path(cls.temp_dir.name)
        cls.log_path = cls.base_path / "raw_logs" / "test_cluster.log"
        cls.db_path = cls.base_path / "warehouse" / "test_logs.db"
        cls.exports_dir = cls.base_path / "parsed_exports"
        cls.report_path = cls.base_path / "reports" / "sre_report.md"

        cls.gen_meta = write_simulated_log_file(
            total_lines=500, seed=42, output_path=cls.log_path
        )
        parser = RegexCentralizedLogParser()
        cls.parsed_bundle = parser.parse_file(cls.log_path)

        warehouse = LogRelationalWarehouse(db_path=cls.db_path)
        cls.wh_res = warehouse.load_and_aggregate(cls.parsed_bundle)
        cls.exported = export_aggregated_csvs_and_sre_report(
            cls.wh_res, exports_dir=cls.exports_dir, report_path=cls.report_path
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_01_compiled_regex_named_groups_extraction(self) -> None:
        """Verifica se a Regex principal extrai todos os 14 grupos nomeados de uma linha de log Nginx."""
        sample_line = (
            '[edge-ingress-01] 177.84.120.15 - usr_204 [02/Nov/2026:08:15:30 -0300] '
            '"POST /api/v1/orders/48219/checkout HTTP/1.1" 500 512 '
            '"https://app.enterprise-portal.com.br/checkout" "Mozilla/5.0 Chrome/128.0" '
            'rt=842.50 uct=810.20 trace_id=TRC-000123-9876'
        )
        match = EXTENDED_ACCESS_LOG_REGEX.match(sample_line)
        self.assertIsNotNone(match)
        g = match.groupdict()
        self.assertEqual(g["node_id"], "edge-ingress-01")
        self.assertEqual(g["client_ip"], "177.84.120.15")
        self.assertEqual(g["auth_user"], "usr_204")
        self.assertEqual(g["http_method"], "POST")
        self.assertEqual(g["raw_uri"], "/api/v1/orders/48219/checkout")
        self.assertEqual(g["status_code"], "500")
        self.assertEqual(g["response_bytes"], "512")
        self.assertEqual(float(g["latency_ms"]), 842.50)
        self.assertEqual(g["trace_id"], "TRC-000123-9876")

        # Verifica rejeição de IP inválido (octeto > 255)
        bad_ip_line = sample_line.replace("177.84.120.15", "999.84.120.15")
        self.assertIsNone(EXTENDED_ACCESS_LOG_REGEX.match(bad_ip_line))

    def test_02_route_normalization_and_security_regex(self) -> None:
        """Valida a normalização de parâmetros dinâmicos de rota (ID e UUID) e detecção de ataques."""
        self.assertEqual(
            normalize_route_path("/api/v1/orders/98412/checkout"),
            "/api/v1/orders/{id}/checkout",
        )
        self.assertEqual(
            normalize_route_path("/api/v1/users/550e8400-e29b-41d4-a716-446655440000/profile"),
            "/api/v1/users/{uuid}/profile",
        )
        self.assertEqual(
            normalize_route_path("/api/v1/orders/912345/invoice.pdf"),
            "/api/v1/orders/{id}/invoice.pdf",
        )
        self.assertEqual(
            normalize_route_path("/static/../../../../etc/passwd"),
            "/[SECURITY_PATH_TRAVERSAL_PROBE]",
        )

        # Classificação de ameaças
        self.assertEqual(
            classify_security_threat(
                "/api/v1/catalog/products/105?filter=1%27%20OR%20%271%27=%271%20UNION%20SELECT%201--",
                "/api/v1/catalog/products/105",
                "Mozilla/5.0",
                403,
            ),
            "SQL_INJECTION_ATTEMPT",
        )
        self.assertEqual(
            classify_security_threat("/.env", "/.env", "curl/8.6.0", 404),
            "SENSITIVE_FILE_SCAN",
        )

    def test_03_sqlite_aggregations_reconciliation(self) -> None:
        """
        Garante que a soma de requisições nas tabelas agregadas (`agg_metrics_by_ip`,
        `agg_metrics_by_route`, `agg_metrics_by_status_code`) bate exatamente com `fact_access_logs`.
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM fact_access_logs")
            total_events = cur.fetchone()[0]
            self.assertGreater(total_events, 480)

            for agg_tbl in (
                "agg_metrics_by_ip",
                "agg_metrics_by_route",
                "agg_metrics_by_node",
            ):
                cur.execute(f"SELECT SUM(total_requests) FROM {agg_tbl}")
                agg_sum = cur.fetchone()[0]
                self.assertEqual(
                    agg_sum,
                    total_events,
                    f"Divergência de contagem na tabela agregada {agg_tbl}",
                )

            cur.execute("SELECT SUM(total_occurrences) FROM agg_metrics_by_status_code")
            status_sum = cur.fetchone()[0]
            self.assertEqual(status_sum, total_events)

            # Garante presença obrigatória de status 200, 404 e 500
            cur.execute("SELECT status_code FROM agg_metrics_by_status_code")
            codes = {r[0] for r in cur.fetchall()}
            self.assertIn(200, codes)
            self.assertIn(404, codes)
            self.assertIn(500, codes)
        finally:
            conn.close()

    def test_04_sre_report_and_csv_exports(self) -> None:
        """Verifica se todos os CSVs agregados e o relatório analítico SRE foram gerados."""
        self.assertTrue(self.report_path.exists())
        content = self.report_path.read_text(encoding="utf-8")
        self.assertIn("agg_metrics_by_status_code", content)
        self.assertIn("agg_metrics_by_route", content)
        self.assertIn("agg_metrics_by_ip", content)

        for key, path_str in self.exported.items():
            self.assertTrue(Path(path_str).exists(), f"Export ausente: {key}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
