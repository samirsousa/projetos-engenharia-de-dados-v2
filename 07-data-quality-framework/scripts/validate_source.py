"""
CLI de Data Quality Gate para pipelines CI/CD, Airflow ou Dagster.

Permite validar qualquer arquivo CSV, Parquet ou tabela SQLite contra um arquivo
JSON de Data Contract (`--contract`), gerando log de anomalias e alerta em texto.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DQConfig, setup_logger
from src.connectors import BaseDataConnector, CSVDataConnector, ParquetDataConnector, SQLiteDataConnector
from src.contracts import DataContract
from src.observability import ObservabilityReporter
from src.validators import DataQualityEngine

logger = setup_logger("DQ-CLI-Gate")


def build_connector(source_format: str, source_path: Path, table_name: str | None) -> BaseDataConnector:
    fmt = source_format.upper()
    if fmt == "CSV":
        return CSVDataConnector(source_path)
    if fmt == "PARQUET":
        return ParquetDataConnector(source_path)
    if fmt == "SQLITE":
        if not table_name:
            raise ValueError("Para formato SQLITE é obrigatório informar --table <nome_da_tabela>.")
        return SQLiteDataConnector(source_path, table_name=table_name)
    raise ValueError(f"Formato não suportado: {source_format}. Use CSV, PARQUET ou SQLITE.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida uma fonte de dados (CSV, Parquet ou SQLite) contra um Data Contract JSON."
    )
    parser.add_argument(
        "--format",
        required=True,
        choices=["CSV", "PARQUET", "SQLITE", "csv", "parquet", "sqlite"],
        help="Formato da fonte de dados (CSV, PARQUET ou SQLITE).",
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Caminho do arquivo CSV, Parquet ou banco de dados SQLite (.db).",
    )
    parser.add_argument(
        "--table",
        type=str,
        default=None,
        help="Nome da tabela (obrigatório quando --format=SQLITE).",
    )
    parser.add_argument(
        "--contract",
        required=True,
        type=Path,
        help="Caminho do arquivo JSON contendo o Data Contract.",
    )
    parser.add_argument(
        "--fail-on-violation",
        action="store_true",
        help="Retorna exit code 1 caso o contrato seja violado (Circuit Breaker CI/CD).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = DQConfig()
    config.ensure_directories()

    contract = DataContract.from_json(args.contract)
    connector = build_connector(args.format, args.source, args.table)
    dataset = connector.load()

    engine = DataQualityEngine()
    reporter = ObservabilityReporter(config=config)

    report = engine.evaluate(dataset, contract)
    reporter.write_anomaly_logs(report)
    reporter.dispatch_alert_if_needed(report, print_to_console=True)

    if not report.contract_passed and args.fail_on_violation:
        logger.error("Quality Gate reprovado para %s. Encerrando com código de erro 1.", dataset.source_name)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
