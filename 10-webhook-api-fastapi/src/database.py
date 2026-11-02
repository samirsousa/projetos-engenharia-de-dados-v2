"""
Camada de Persistência Relacional em SQLite (`WebhookEventRepository`).

Gerencia o armazenamento transacional dos eventos operacionais validados e a
fila de mensagens rejeitadas (`dead_letter_webhooks`) para governança e auditoria.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from src.schemas import (
    BatchWebhookIngestResponse,
    DeadLetterItemResponse,
    EnvironmentType,
    EventCategory,
    LogSeverity,
    OperationalAnalyticsSummary,
    PaginatedEventsResponse,
    StoredWebhookEvent,
    TelemetryMetrics,
    WebhookEventCreate,
    WebhookIngestResponse,
)


class DuplicateWebhookEventError(Exception):
    """Levantada quando um `event_id` já foi processado anteriormente (Idempotência)."""

    def __init__(self, event_id: str) -> None:
        super().__init__(f"O evento '{event_id}' já foi registrado anteriormente.")
        self.event_id = event_id


class WebhookEventNotFoundError(Exception):
    """Levantada quando um `event_id` consultado não existe no banco relacional."""

    def __init__(self, event_id: str) -> None:
        super().__init__(f"Evento operacional '{event_id}' não encontrado.")
        self.event_id = event_id


class WebhookAuthError(Exception):
    """Levantada quando a assinatura HMAC-SHA256 do Webhook está ausente ou inválida."""


GATEWAY_DDL_SCRIPT = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS operational_events (
    event_id            TEXT PRIMARY KEY,
    event_type          TEXT NOT NULL,
    severity            TEXT NOT NULL,
    environment         TEXT NOT NULL,
    service_name        TEXT NOT NULL,
    host_ip             TEXT NOT NULL,
    trace_id            TEXT,
    event_timestamp_utc TEXT NOT NULL,
    received_at_utc     TEXT NOT NULL,
    message             TEXT NOT NULL,
    latency_ms          REAL NOT NULL,
    cpu_usage_pct       REAL,
    memory_mb           REAL,
    http_status_code    INTEGER,
    tags_json           TEXT NOT NULL,
    payload_context_json TEXT NOT NULL,
    payload_sha256      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_op_events_service ON operational_events(service_name);
CREATE INDEX IF NOT EXISTS idx_op_events_severity ON operational_events(severity);
CREATE INDEX IF NOT EXISTS idx_op_events_type ON operational_events(event_type);
CREATE INDEX IF NOT EXISTS idx_op_events_env ON operational_events(environment);
CREATE INDEX IF NOT EXISTS idx_op_events_ts ON operational_events(event_timestamp_utc);

CREATE TABLE IF NOT EXISTS dead_letter_webhooks (
    dlq_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at_utc     TEXT NOT NULL,
    endpoint            TEXT NOT NULL,
    http_status         INTEGER NOT NULL,
    error_code          TEXT NOT NULL,
    error_summary       TEXT NOT NULL,
    raw_payload_preview TEXT NOT NULL
);
"""


class WebhookEventRepository:
    """Repositório relacional de eventos de Webhook e auditoria de Dead-Letter Queue."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(GATEWAY_DDL_SCRIPT)

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    @staticmethod
    def _compute_payload_hash(event: WebhookEventCreate) -> str:
        canonical = json.dumps(event.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def insert_event(self, event: WebhookEventCreate) -> WebhookIngestResponse:
        """Persiste um único evento de webhook validado ou levanta `DuplicateWebhookEventError`."""
        now_iso = self._utc_now_iso()
        payload_hash = self._compute_payload_hash(event)

        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT 1 FROM operational_events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            if existing:
                raise DuplicateWebhookEventError(event.event_id)

            conn.execute(
                """
                INSERT INTO operational_events (
                    event_id, event_type, severity, environment, service_name,
                    host_ip, trace_id, event_timestamp_utc, received_at_utc,
                    message, latency_ms, cpu_usage_pct, memory_mb, http_status_code,
                    tags_json, payload_context_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event_type.value,
                    event.severity.value,
                    event.environment.value,
                    event.service_name,
                    event.host_ip,
                    event.trace_id,
                    event.event_timestamp_utc,
                    now_iso,
                    event.message,
                    event.metrics.latency_ms,
                    event.metrics.cpu_usage_pct,
                    event.metrics.memory_mb,
                    event.metrics.http_status_code,
                    json.dumps(event.tags, ensure_ascii=False),
                    json.dumps(event.payload_context, ensure_ascii=False),
                    payload_hash,
                ),
            )

        return WebhookIngestResponse(
            status="ACCEPTED",
            event_id=event.event_id,
            service_name=event.service_name,
            severity=event.severity,
            received_at_utc=now_iso,
            payload_sha256=payload_hash,
        )

    def insert_batch_events(
        self, events: List[WebhookEventCreate]
    ) -> BatchWebhookIngestResponse:
        """Persiste um lote de eventos com deduplicação automática de IDs já existentes."""
        now_iso = self._utc_now_iso()
        inserted_ids: List[str] = []
        skipped_duplicates = 0

        with self._get_conn() as conn:
            for event in events:
                existing = conn.execute(
                    "SELECT 1 FROM operational_events WHERE event_id = ?",
                    (event.event_id,),
                ).fetchone()
                if existing:
                    skipped_duplicates += 1
                    continue

                payload_hash = self._compute_payload_hash(event)
                conn.execute(
                    """
                    INSERT INTO operational_events (
                        event_id, event_type, severity, environment, service_name,
                        host_ip, trace_id, event_timestamp_utc, received_at_utc,
                        message, latency_ms, cpu_usage_pct, memory_mb, http_status_code,
                        tags_json, payload_context_json, payload_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.event_type.value,
                        event.severity.value,
                        event.environment.value,
                        event.service_name,
                        event.host_ip,
                        event.trace_id,
                        event.event_timestamp_utc,
                        now_iso,
                        event.message,
                        event.metrics.latency_ms,
                        event.metrics.cpu_usage_pct,
                        event.metrics.memory_mb,
                        event.metrics.http_status_code,
                        json.dumps(event.tags, ensure_ascii=False),
                        json.dumps(event.payload_context, ensure_ascii=False),
                        payload_hash,
                    ),
                )
                inserted_ids.append(event.event_id)

        return BatchWebhookIngestResponse(
            status="BATCH_PROCESSED",
            total_received=len(events),
            inserted_count=len(inserted_ids),
            duplicate_skipped_count=skipped_duplicates,
            processed_at_utc=now_iso,
            inserted_event_ids=inserted_ids,
        )

    @staticmethod
    def _row_to_stored_event(row: sqlite3.Row) -> StoredWebhookEvent:
        return StoredWebhookEvent(
            event_id=str(row["event_id"]),
            event_type=EventCategory(row["event_type"]),
            severity=LogSeverity(row["severity"]),
            environment=EnvironmentType(row["environment"]),
            service_name=str(row["service_name"]),
            host_ip=str(row["host_ip"]),
            trace_id=row["trace_id"],
            event_timestamp_utc=str(row["event_timestamp_utc"]),
            received_at_utc=str(row["received_at_utc"]),
            message=str(row["message"]),
            metrics=TelemetryMetrics(
                latency_ms=float(row["latency_ms"]),
                cpu_usage_pct=float(row["cpu_usage_pct"]) if row["cpu_usage_pct"] is not None else None,
                memory_mb=float(row["memory_mb"]) if row["memory_mb"] is not None else None,
                http_status_code=int(row["http_status_code"]) if row["http_status_code"] is not None else None,
            ),
            tags=json.loads(row["tags_json"]),
            payload_context=json.loads(row["payload_context_json"]),
            payload_sha256=str(row["payload_sha256"]),
        )

    def get_event_by_id(self, event_id: str) -> StoredWebhookEvent:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM operational_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        if not row:
            raise WebhookEventNotFoundError(event_id)
        return self._row_to_stored_event(row)

    def query_events(
        self,
        service_name: Optional[str] = None,
        event_type: Optional[EventCategory] = None,
        severity: Optional[LogSeverity] = None,
        environment: Optional[EnvironmentType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedEventsResponse:
        clauses: List[str] = []
        params: List[Any] = []

        if service_name:
            clauses.append("service_name = ?")
            params.append(service_name)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type.value)
        if severity:
            clauses.append("severity = ?")
            params.append(severity.value)
        if environment:
            clauses.append("environment = ?")
            params.append(environment.value)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._get_conn() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) AS cnt FROM operational_events {where_sql}",
                    tuple(params),
                ).fetchone()["cnt"]
            )
            rows = conn.execute(
                f"""
                SELECT * FROM operational_events
                {where_sql}
                ORDER BY event_timestamp_utc DESC
                LIMIT ? OFFSET ?
                """,
                tuple(params + [limit, offset]),
            ).fetchall()

        return PaginatedEventsResponse(
            total_matching=total,
            limit=limit,
            offset=offset,
            items=[self._row_to_stored_event(r) for r in rows],
        )

    def record_dead_letter(
        self,
        endpoint: str,
        http_status: int,
        error_code: str,
        error_summary: str,
        raw_payload_preview: str,
    ) -> None:
        now_iso = self._utc_now_iso()
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO dead_letter_webhooks (
                    received_at_utc, endpoint, http_status,
                    error_code, error_summary, raw_payload_preview
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso,
                    endpoint,
                    http_status,
                    error_code,
                    error_summary[:500],
                    raw_payload_preview[:1000],
                ),
            )

    def list_dead_letters(self, limit: int = 50) -> List[DeadLetterItemResponse]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dead_letter_webhooks ORDER BY dlq_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            DeadLetterItemResponse(
                dlq_id=int(r["dlq_id"]),
                received_at_utc=str(r["received_at_utc"]),
                endpoint=str(r["endpoint"]),
                http_status=int(r["http_status"]),
                error_code=str(r["error_code"]),
                error_summary=str(r["error_summary"]),
                raw_payload_preview=str(r["raw_payload_preview"]),
            )
            for r in rows
        ]

    def get_analytics_summary(self) -> OperationalAnalyticsSummary:
        with self._get_conn() as conn:
            agg = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_events,
                    COALESCE(ROUND(AVG(latency_ms), 2), 0.0) AS avg_lat,
                    COALESCE(ROUND(MAX(latency_ms), 2), 0.0) AS max_lat,
                    COALESCE(ROUND(AVG(cpu_usage_pct), 2), 0.0) AS avg_cpu
                  FROM operational_events
                """
            ).fetchone()

            dlq_cnt = int(
                conn.execute("SELECT COUNT(*) AS cnt FROM dead_letter_webhooks").fetchone()["cnt"]
            )

            by_sev = {
                str(r["severity"]): int(r["cnt"])
                for r in conn.execute(
                    "SELECT severity, COUNT(*) AS cnt FROM operational_events GROUP BY severity"
                ).fetchall()
            }
            by_cat = {
                str(r["event_type"]): int(r["cnt"])
                for r in conn.execute(
                    "SELECT event_type, COUNT(*) AS cnt FROM operational_events GROUP BY event_type"
                ).fetchall()
            }
            by_env = {
                str(r["environment"]): int(r["cnt"])
                for r in conn.execute(
                    "SELECT environment, COUNT(*) AS cnt FROM operational_events GROUP BY environment"
                ).fetchall()
            }
            top_svcs = [
                {
                    "service_name": str(r["service_name"]),
                    "event_count": int(r["cnt"]),
                    "avg_latency_ms": float(r["avg_lat"]),
                }
                for r in conn.execute(
                    """
                    SELECT
                        service_name,
                        COUNT(*) AS cnt,
                        ROUND(AVG(latency_ms), 2) AS avg_lat
                      FROM operational_events
                     GROUP BY service_name
                     ORDER BY cnt DESC
                     LIMIT 10
                    """
                ).fetchall()
            ]

        return OperationalAnalyticsSummary(
            total_events_stored=int(agg["total_events"]),
            total_dead_letter_rejections=dlq_cnt,
            avg_latency_ms=float(agg["avg_lat"]),
            max_latency_ms=float(agg["max_lat"]),
            avg_cpu_usage_pct=float(agg["avg_cpu"]),
            events_by_severity=by_sev,
            events_by_category=by_cat,
            events_by_environment=by_env,
            top_services=top_svcs,
        )
