"""
Orquestrador Principal da Suíte de Data Quality & Observability.

Executa a validação completa de Data Contracts sobre:
1. Arquivos CSV (`financial_transactions.csv`)
2. Arquivos Apache Parquet (`iot_sensor_telemetry.parquet`)
3. Tabelas SQLite (`crm_warehouse.db::customers_silver` e `crm_warehouse.db::customers_gold_clean`)

Gera logs estruturados de anomalias (Data Contract Violations), emite alertas formatados
em texto no terminal e em disco, e consolida o relatório executivo em Markdown.
"""

from __future__ import annotations

import argparse
import shutil
from typing import List

from src.config import DQConfig, setup_logger
from src.connectors import CSVDataConnector, ParquetDataConnector, SQLiteDataConnector
from src.contracts import ValidationReport
from src.observability import ObservabilityReporter
from src.sample_factory import (
    build_csv_transactions_sample,
    build_parquet_telemetry_sample,
    build_sqlite_customers_samples,
)
from src.validators import DataQualityEngine

logger = setup_logger("DQ-Orchestrator")


def run_full_dq_observability_suite(clean_start: bool = False, quiet_alerts: bool = False) -> List[ValidationReport]:
    config = DQConfig()

    if clean_start:
        for folder in (config.data_dir, config.logs_dir, config.reports_dir):
            if folder.exists():
                shutil.rmtree(folder)

    config.ensure_directories()

    logger.info("=" * 88)
    logger.info("INICIANDO FRAMEWORK DE DATA QUALITY & OBSERVABILITY (CSV / PARQUET / SQLITE)")
    logger.info("=" * 88)

    # 1. Prepara fontes de dados e contratos declarativos JSON
    csv_path, csv_contract = build_csv_transactions_sample(config)
    parquet_path, parquet_contract = build_parquet_telemetry_sample(config)
    sqlite_path, sqlite_silver_contract, sqlite_gold_contract = build_sqlite_customers_samples(config)

    engine = DataQualityEngine()
    reporter = ObservabilityReporter(config=config)
    reports: List[ValidationReport] = []

    evaluation_targets = [
        ("CSV", CSVDataConnector(csv_path), csv_contract),
        ("PARQUET", ParquetDataConnector(parquet_path), parquet_contract),
        ("SQLITE (Silver - Com Anomalias)", SQLiteDataConnector(sqlite_path, "customers_silver"), sqlite_silver_contract),
        ("SQLITE (Gold - Limpo/Conforme)", SQLiteDataConnector(sqlite_path, "customers_gold_clean"), sqlite_gold_contract),
    ]

    for label, connector, contract in evaluation_targets:
        logger.info("-" * 88)
        logger.info("Inspecionando Fonte [%s] -> Contrato: %s (%s)", label, contract.contract_id, contract.dataset_name)
        dataset = connector.load()
        report = engine.evaluate(dataset, contract)
        reports.append(report)

        reporter.write_anomaly_logs(report)
        reporter.dispatch_alert_if_needed(report, print_to_console=not quiet_alerts)

    md_report_path = reporter.generate_consolidated_markdown_report(reports)

    logger.info("=" * 88)
    logger.info("RESUMO EXECUTIVO DA SUÍTE DE DATA QUALITY & OBSERVABILITY")
    for rep in reports:
        status_str = "PASS (CONFORME)" if rep.contract_passed else "FAIL (CONTRACT VIOLATION)"
        logger.info(
            "  %-32s | %-7s | DQ Score: %6.2f%% | Anomalias: %2d | %s",
            rep.contract.dataset_name,
            rep.contract.source_format,
            rep.data_quality_score,
            len(rep.anomalies),
            status_str,
        )
    logger.info("  Log Central de Violações : %s", config.anomalies_dir / "data_contract_violations.log")
    logger.info("  Diretório de Alertas TXT : %s", config.alerts_dir)
    logger.info("  Relatório Consolidado MD : %s", md_report_path)
    logger.info("=" * 88)

    return reports


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa a suíte completa do Data Quality & Observability Framework."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Limpa diretórios data/, logs/ e reports/ antes de iniciar.",
    )
    parser.add_argument(
        "--quiet-alerts",
        action="store_true",
        help="Salva os alertas em arquivo sem imprimi-los na saída padrão.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_full_dq_observability_suite(clean_start=args.clean, quiet_alerts=args.quiet_alerts)
