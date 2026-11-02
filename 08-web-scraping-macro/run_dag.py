"""
Orquestrador Customizado de Execução em DAG Sequencial (Simulador Airflow / Cron Scheduler).

Executa o grafo completo de tarefas:
  [t1_verify_portal_ethics] >> [t2_extract_raw_html] >> [t3_clean_and_type_schema] >> [t4_quality_gate] >> [t5_load_sqlite_warehouse]

Persiste o manifesto de execução da DAG em `logs/dag_run_<id>.json`, registra a auditoria
na tabela `dag_execution_history` do SQLite e exibe o resumo de telemetria de cada nó.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict

from src.config import ScrapingPipelineConfig, setup_logger
from src.dag_orchestrator import DAGRunResult, TaskState, build_macro_scraping_dag
from src.loader import MacroWarehouseLoader

logger = setup_logger("Macro-Scheduler")


def run_scheduled_dag(clean_start: bool = False, simulate_failures: int = 1) -> DAGRunResult:
    config = ScrapingPipelineConfig()

    if clean_start:
        for directory in (config.data_dir, config.logs_dir, config.reports_dir):
            if directory.exists():
                shutil.rmtree(directory)

    config.ensure_directories()

    dag = build_macro_scraping_dag(
        config=config,
        simulate_transient_failures=simulate_failures,
    )

    print("\n" + dag.render_ascii_graph() + "\n")
    result = dag.execute()

    # Persiste histórico de execução da DAG no SQLite Warehouse
    records_loaded = int(
        result.xcom_snapshot.get("t5_load_sqlite_warehouse", {}).get("records_loaded", 0)
    )
    succeeded_count = sum(1 for t in result.task_telemetries if t.state == TaskState.SUCCESS)

    loader = MacroWarehouseLoader(config=config)
    loader.record_dag_execution(
        dag_run_id=result.dag_run_id,
        dag_id=result.dag_id,
        schedule_cron=result.schedule_cron,
        started_at_utc=result.started_at_utc,
        finished_at_utc=result.finished_at_utc,
        status=result.overall_status,
        tasks_total=len(result.task_telemetries),
        tasks_succeeded=succeeded_count,
        total_duration_ms=result.total_duration_ms,
        records_loaded=records_loaded,
    )

    manifest_path = config.logs_dir / f"dag_run_{result.dag_run_id}.json"
    latest_manifest_path = config.logs_dir / "latest_dag_run.json"
    for path in (manifest_path, latest_manifest_path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(result), fh, indent=2, ensure_ascii=False)

    logger.info("=" * 90)
    logger.info("RESUMO DE EXECUÇÃO DA DAG | %s (%s)", result.dag_id, result.overall_status)
    logger.info("-" * 90)
    for t_tel in result.task_telemetries:
        logger.info(
            "  Task: %-28s | Status: %-15s | Tentativas: %d | Duração: %7.2f ms",
            t_tel.task_id,
            t_tel.state.value,
            t_tel.attempts,
            t_tel.duration_ms,
        )
    logger.info("-" * 90)
    logger.info("  Duração Total da DAG : %.2f ms", result.total_duration_ms)
    logger.info("  Registros no SQLite  : %s", result.xcom_snapshot.get("t5_load_sqlite_warehouse", {}).get("total_db_rows", 0))
    logger.info("  Banco SQLite         : %s", config.sqlite_db_path)
    logger.info("  Relatório Analítico  : %s", config.reports_dir / "macro_economic_summary.md")
    logger.info("  Manifesto JSON DAG   : %s", manifest_path)
    logger.info("=" * 90)

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulador de Orquestração DAG (Airflow/Cron) para Pipeline Macroeconômico."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Limpa os diretórios data/, logs/ e reports/ antes de executar a DAG.",
    )
    parser.add_argument(
        "--simulate-failures",
        type=int,
        default=1,
        help="Número de erros HTTP 503 transitórios a injetar na extração para testar Retry Logic (padrão: 1).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_scheduled_dag(clean_start=args.clean, simulate_failures=args.simulate_failures)
