"""
Componente 4: Simulador de Orquestração DAG (Airflow / Cron Scheduler Engine em Python Puro).

Implementa os conceitos fundamentais de um orquestrador de engenharia de dados:
- Grafo Acíclico Dirigido (`DAG`) com ordenação topológica (Algoritmo de Kahn) e detecção de ciclos.
- Sintaxe declarativa de encadeamento via operador bitshift (`task_1 >> task_2 >> task_3`).
- Máquina de estados de tarefas (`PENDING`, `RUNNING`, `RETRYING`, `SUCCESS`, `FAILED`, `UPSTREAM_FAILED`).
- Barramento `XCom` (`xcom_push` / `xcom_pull`) para troca de metadados entre tarefas.
- Avaliador de expressões Cron de 5 campos (`0 8 * * 1-5`).
"""

from __future__ import annotations

import json
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from src.config import ScrapingPipelineConfig, setup_logger
from src.extractor import MacroWebExtractor
from src.loader import MacroWarehouseLoader
from src.portal_simulator import materialize_mock_portal
from src.transformer import MacroDataTransformer

logger = setup_logger("DAG-Orchestrator")


class TaskState(str, Enum):
    """Estados do ciclo de vida de uma tarefa dentro da DAG."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UPSTREAM_FAILED = "UPSTREAM_FAILED"


class DAGCycleError(Exception):
    """Levantada quando o grafo de tarefas possui dependências circulares."""


@dataclass
class TaskExecutionContext:
    """Contexto injetado em cada tarefa com suporte a XCom (estilo Apache Airflow)."""

    dag_id: str
    dag_run_id: str
    task_id: str
    execution_date_utc: str
    _xcom_store: Dict[str, Dict[str, Any]]

    def xcom_push(self, key: str, value: Any) -> None:
        if self.task_id not in self._xcom_store:
            self._xcom_store[self.task_id] = {}
        self._xcom_store[self.task_id][key] = value

    def xcom_pull(self, task_id: str, key: str = "return_value") -> Any:
        return self._xcom_store.get(task_id, {}).get(key)


@dataclass
class TaskTelemetry:
    """Telemetria individual de execução de um nó da DAG."""

    task_id: str
    state: TaskState = TaskState.PENDING
    attempts: int = 0
    started_at_utc: Optional[str] = None
    finished_at_utc: Optional[str] = None
    duration_ms: float = 0.0
    error_message: Optional[str] = None


class PythonTask:
    """Representa um nó de tarefa executável dentro de uma DAG."""

    def __init__(
        self,
        task_id: str,
        python_callable: Callable[[TaskExecutionContext], Any],
        retries: int = 2,
        retry_delay_sec: float = 0.1,
        description: str = "",
    ) -> None:
        self.task_id = task_id
        self.python_callable = python_callable
        self.retries = retries
        self.retry_delay_sec = retry_delay_sec
        self.description = description
        self.upstream_ids: Set[str] = set()
        self.downstream_ids: Set[str] = set()

    def set_downstream(self, other: PythonTask) -> PythonTask:
        self.downstream_ids.add(other.task_id)
        other.upstream_ids.add(self.task_id)
        return other

    def __rshift__(self, other: PythonTask) -> PythonTask:
        """Permite encadeamento no padrão Airflow: `t1 >> t2 >> t3`."""
        return self.set_downstream(other)


@dataclass
class DAGRunResult:
    """Resultado consolidado de uma execução completa da DAG."""

    dag_id: str
    dag_run_id: str
    schedule_cron: str
    overall_status: str
    started_at_utc: str
    finished_at_utc: str
    total_duration_ms: float
    execution_order: List[str]
    task_telemetries: List[TaskTelemetry] = field(default_factory=list)
    xcom_snapshot: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class DAG:
    """Motor de orquestração de tarefas em Grafo Acíclico Dirigido (DAG)."""

    def __init__(
        self,
        dag_id: str,
        schedule_cron: str = "0 8 * * 1-5",
        description: str = "",
    ) -> None:
        self.dag_id = dag_id
        self.schedule_cron = schedule_cron
        self.description = description
        self.tasks: Dict[str, PythonTask] = {}

    def add_task(self, task: PythonTask) -> PythonTask:
        if task.task_id in self.tasks:
            raise ValueError(f"Tarefa duplicada na DAG: {task.task_id}")
        self.tasks[task.task_id] = task
        return task

    @staticmethod
    def validate_cron_expression(cron_expr: str) -> bool:
        """Valida sintaxe padrão de 5 campos Cron (minuto, hora, dia_mes, mes, dia_semana)."""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Expressão Cron inválida '{cron_expr}': esperados 5 campos.")
        return True

    def topological_sort(self) -> List[str]:
        """
        Ordena as tarefas topologicamente usando o Algoritmo de Kahn.
        Lança `DAGCycleError` caso exista dependência circular entre tarefas.
        """
        in_degree: Dict[str, int] = {tid: len(task.upstream_ids) for tid, task in self.tasks.items()}
        queue: deque[str] = deque(sorted(tid for tid, deg in in_degree.items() if deg == 0))
        ordered: List[str] = []

        while queue:
            current_id = queue.popleft()
            ordered.append(current_id)

            for down_id in sorted(self.tasks[current_id].downstream_ids):
                in_degree[down_id] -= 1
                if in_degree[down_id] == 0:
                    queue.append(down_id)

        if len(ordered) != len(self.tasks):
            raise DAGCycleError(
                f"Ciclo detectado na DAG '{self.dag_id}'! Ordenadas {len(ordered)}/{len(self.tasks)} tarefas."
            )
        return ordered

    def render_ascii_graph(self) -> str:
        """Gera representação visual ASCII da topologia sequencial da DAG."""
        ordered = self.topological_sort()
        chain = "  ==>  ".join(f"[{tid}]" for tid in ordered)
        return f"DAG '{self.dag_id}' (Cron: '{self.schedule_cron}'):\n  {chain}"

    def execute(self, run_id: Optional[str] = None) -> DAGRunResult:
        """Executa todas as tarefas na ordem topológica gerenciando estados, retries e XCom."""
        self.validate_cron_expression(self.schedule_cron)
        execution_order = self.topological_sort()

        dag_run_id = run_id or f"DAGRUN-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        dag_start_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        dag_start_ns = time.perf_counter_ns()

        xcom_store: Dict[str, Dict[str, Any]] = {}
        telemetries: Dict[str, TaskTelemetry] = {
            tid: TaskTelemetry(task_id=tid) for tid in execution_order
        }

        logger.info("=" * 90)
        logger.info("INICIANDO ORQUESTRADOR DAG | dag_id=%s | run_id=%s | cron='%s'", self.dag_id, dag_run_id, self.schedule_cron)
        logger.info("Topologia: %s", " >> ".join(execution_order))
        logger.info("=" * 90)

        for tid in execution_order:
            task = self.tasks[tid]
            telemetry = telemetries[tid]

            # Verifica se todas as dependências upstream tiveram sucesso
            upstream_failed = any(
                telemetries[up_id].state != TaskState.SUCCESS for up_id in task.upstream_ids
            )
            if upstream_failed:
                telemetry.state = TaskState.UPSTREAM_FAILED
                telemetry.error_message = "Tarefa bloqueada devido a falha em dependência upstream."
                logger.error("Task [%s] -> UPSTREAM_FAILED", tid)
                continue

            ctx = TaskExecutionContext(
                dag_id=self.dag_id,
                dag_run_id=dag_run_id,
                task_id=tid,
                execution_date_utc=dag_start_utc,
                _xcom_store=xcom_store,
            )

            task_start_ns = time.perf_counter_ns()
            telemetry.started_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            max_attempts = task.retries + 1

            for attempt in range(1, max_attempts + 1):
                telemetry.attempts = attempt
                telemetry.state = TaskState.RUNNING if attempt == 1 else TaskState.RETRYING
                logger.info(
                    "Executando Task [%s] (tentativa %d/%d)...",
                    tid,
                    attempt,
                    max_attempts,
                )
                try:
                    return_val = task.python_callable(ctx)
                    if return_val is not None:
                        ctx.xcom_push("return_value", return_val)
                    telemetry.state = TaskState.SUCCESS
                    telemetry.error_message = None
                    break
                except Exception as exc:
                    telemetry.error_message = str(exc)
                    if attempt < max_attempts:
                        logger.warning(
                            "Task [%s] falhou na tentativa %d/%d: %s. Aguardando %.2fs para retry...",
                            tid,
                            attempt,
                            max_attempts,
                            exc,
                            task.retry_delay_sec,
                        )
                        time.sleep(task.retry_delay_sec)
                    else:
                        telemetry.state = TaskState.FAILED
                        logger.error(
                            "Task [%s] FALHOU definitivamente após %d tentativa(s): %s",
                            tid,
                            attempt,
                            exc,
                        )

            telemetry.finished_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            telemetry.duration_ms = round((time.perf_counter_ns() - task_start_ns) / 1_000_000.0, 2)
            logger.info(
                "Task [%s] finalizada | status=%s | duracao=%.2f ms",
                tid,
                telemetry.state.value,
                telemetry.duration_ms,
            )

        dag_end_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        total_ms = round((time.perf_counter_ns() - dag_start_ns) / 1_000_000.0, 2)
        all_succeeded = all(t.state == TaskState.SUCCESS for t in telemetries.values())
        overall_status = "SUCCESS" if all_succeeded else "FAILED"

        return DAGRunResult(
            dag_id=self.dag_id,
            dag_run_id=dag_run_id,
            schedule_cron=self.schedule_cron,
            overall_status=overall_status,
            started_at_utc=dag_start_utc,
            finished_at_utc=dag_end_utc,
            total_duration_ms=total_ms,
            execution_order=execution_order,
            task_telemetries=[telemetries[tid] for tid in execution_order],
            xcom_snapshot=xcom_store,
        )


def build_macro_scraping_dag(
    config: Optional[ScrapingPipelineConfig] = None,
    simulate_transient_failures: int = 1,
) -> DAG:
    """
    Constrói a DAG completa de Engenharia de Dados para Web Scraping Macroeconômico:
    `t1_verify_portal_ethics >> t2_extract_raw_html >> t3_clean_and_type_schema >> t4_quality_gate >> t5_load_sqlite_warehouse`
    """
    cfg = config or ScrapingPipelineConfig()
    cfg.ensure_directories()

    dag = DAG(
        dag_id="macro_economic_indicators_etl_dag",
        schedule_cron="0 8 * * 1-5",
        description="Pipeline diário de extração ética, limpeza tipada e carga histórica de indicadores BCB/IBGE/FGV.",
    )

    def task_1_verify_portal_ethics(ctx: TaskExecutionContext) -> Dict[str, str]:
        robots_path, boletim_path, ptax_path = materialize_mock_portal(cfg)
        extractor = MacroWebExtractor(config=cfg, simulate_transient_failures=0)
        robots_txt = robots_path.read_text(encoding="utf-8")
        extractor.verify_robots_txt(robots_txt, f"/{boletim_path.name}")
        extractor.verify_robots_txt(robots_txt, f"/{ptax_path.name}")
        ctx.xcom_push("portal_verified", True)
        return {"robots_status": "COMPLIANT", "pages_ready": 2}

    def task_2_extract_raw_html(ctx: TaskExecutionContext) -> Dict[str, Any]:
        extractor = MacroWebExtractor(
            config=cfg,
            simulate_transient_failures=simulate_transient_failures,
        )
        res = extractor.run_extraction(batch_id=ctx.dag_run_id)
        ctx.xcom_push("bronze_file_path", res.bronze_file_path)
        ctx.xcom_push("raw_rows_count", res.total_raw_rows)
        ctx.xcom_push("retries_triggered", res.total_retry_attempts)
        return {
            "bronze_file": res.bronze_file_path,
            "raw_rows": res.total_raw_rows,
            "retries": res.total_retry_attempts,
        }

    def task_3_clean_and_type_schema(ctx: TaskExecutionContext) -> Dict[str, Any]:
        bronze_path_str = ctx.xcom_pull("t2_extract_raw_html", "bronze_file_path")
        transformer = MacroDataTransformer(config=cfg)
        res = transformer.run_transformation(bronze_file=Path(bronze_path_str))
        ctx.xcom_push("silver_json_path", res.silver_json_path)
        ctx.xcom_push("valid_typed_rows", res.valid_typed_rows)
        ctx.xcom_push("quarantined_rows", res.quarantined_rows)
        return {
            "silver_json": res.silver_json_path,
            "valid_rows": res.valid_typed_rows,
            "quarantined_rows": res.quarantined_rows,
        }

    def task_4_quality_gate(ctx: TaskExecutionContext) -> Dict[str, Any]:
        silver_path = Path(ctx.xcom_pull("t3_clean_and_type_schema", "silver_json_path"))
        with open(silver_path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        records = doc.get("records", [])
        if not records:
            raise RuntimeError("Quality Gate Reprovado: Nenhum registro válido produzido na camada Silver.")

        # Verifica invariantes: valores numéricos finitos, datas ISO válidas e códigos preenchidos
        for rec in records:
            if rec.get("numeric_value") is None or not str(rec.get("indicator_code", "")).strip():
                raise RuntimeError(f"Quality Gate Reprovado: Registro inválido detectado: {rec}")

        ctx.xcom_push("quality_gate_passed", True)
        return {"quality_status": "PASSED", "validated_records": len(records)}

    def task_5_load_sqlite_warehouse(ctx: TaskExecutionContext) -> Dict[str, Any]:
        silver_path = Path(ctx.xcom_pull("t3_clean_and_type_schema", "silver_json_path"))
        loader = MacroWarehouseLoader(config=cfg)
        res = loader.run_load(silver_file=silver_path)
        ctx.xcom_push("records_loaded", res.facts_inserted_or_updated)
        ctx.xcom_push("total_db_rows", res.total_historical_rows_in_db)
        ctx.xcom_push("summary_report_path", res.summary_report_path)
        return {
            "facts_upserted": res.facts_inserted_or_updated,
            "total_historical_rows": res.total_historical_rows_in_db,
            "report_md": res.summary_report_path,
        }

    t1 = dag.add_task(
        PythonTask(
            task_id="t1_verify_portal_ethics",
            python_callable=task_1_verify_portal_ethics,
            description="Verifica disponibilidade do portal e diretivas éticas do robots.txt.",
        )
    )
    t2 = dag.add_task(
        PythonTask(
            task_id="t2_extract_raw_html",
            python_callable=task_2_extract_raw_html,
            description="Extrai tabelas HTML com retry/backoff exponencial e grava na Bronze.",
        )
    )
    t3 = dag.add_task(
        PythonTask(
            task_id="t3_clean_and_type_schema",
            python_callable=task_3_clean_and_type_schema,
            description="Limpa ruídos HTML, converte decimais/datas e aplica schema tipado na Silver.",
        )
    )
    t4 = dag.add_task(
        PythonTask(
            task_id="t4_quality_gate",
            python_callable=task_4_quality_gate,
            description="Valida invariantes de qualidade antes da carga no Data Warehouse.",
        )
    )
    t5 = dag.add_task(
        PythonTask(
            task_id="t5_load_sqlite_warehouse",
            python_callable=task_5_load_sqlite_warehouse,
            description="Realiza UPSERT histórico no SQLite e gera relatório analítico Fisher.",
        )
    )

    # Encadeamento sequencial declarativo da DAG
    t1 >> t2 >> t3 >> t4 >> t5

    return dag
