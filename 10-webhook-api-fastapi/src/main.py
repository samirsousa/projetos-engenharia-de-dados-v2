"""
Aplicação Principal FastAPI: Webhook Receiver & Operational Logs API Gateway.

Inclui:
- Documentação Interativa Automática (Swagger UI em `/docs` e ReDoc em `/redoc`).
- Validação rigorosa de payloads via Pydantic v2 (`extra="forbid"` + invariantes de domínio).
- Tratamento robusto de exceções com gravação automática em Dead-Letter Queue (`dead_letter_webhooks`).
- Verificação criptográfica HMAC-SHA256 (`X-Webhook-Signature`).
- Persistência relacional transacional em SQLite modo `WAL`.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.config import APIGatewayConfig, setup_logger
from src.database import (
    DuplicateWebhookEventError,
    WebhookAuthError,
    WebhookEventNotFoundError,
    WebhookEventRepository,
)
from src.schemas import (
    BatchWebhookCreate,
    BatchWebhookIngestResponse,
    DeadLetterItemResponse,
    EnvironmentType,
    EventCategory,
    LogSeverity,
    OperationalAnalyticsSummary,
    PaginatedEventsResponse,
    StandardErrorEnvelope,
    StoredWebhookEvent,
    WebhookEventCreate,
    WebhookIngestResponse,
)
from src.security import verify_webhook_signature

logger = setup_logger("FastAPI-Webhook-Gateway")


OPENAPI_TAGS_METADATA = [
    {
        "name": "1. Health & Diagnostics",
        "description": "Monitoramento de disponibilidade (Liveness / Readiness) do API Gateway e banco SQLite.",
    },
    {
        "name": "2. Webhook Ingestion",
        "description": "Recepção de eventos operacionais unitários e em lote com validação estrita Pydantic v2 e assinatura HMAC-SHA256.",
    },
    {
        "name": "3. Operational Logs Query",
        "description": "Consulta paginada e busca por ID dos logs operacionais armazenados no banco relacional.",
    },
    {
        "name": "4. Observability & Dead-Letter Queue",
        "description": "Métricas agregadas de telemetria e auditoria de payloads rejeitados (Dead-Letter Queue).",
    },
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def create_app(custom_config: Optional[APIGatewayConfig] = None) -> FastAPI:
    """Application Factory para instanciar o FastAPI Gateway com injeção de configuração."""
    config = custom_config or APIGatewayConfig()
    config.ensure_directories()
    repository = WebhookEventRepository(db_path=config.sqlite_db_path)

    app = FastAPI(
        title=config.api_title,
        version=config.api_version,
        description=(
            "**API Gateway e Receptor de Webhooks de Logs Operacionais** construído com **FastAPI**, "
            "**Pydantic v2** e **SQLite Relacional (WAL)**.\n\n"
            "### Funcionalidades Principais:\n"
            "- **Schema Enforcement Estrito:** Rejeita campos extras não documentados (`extra='forbid'`), valida IPs, timestamps ISO-8601 e invariantes críticas.\n"
            "- **Idempotência Transacional:** Proteção contra duplicação de `event_id` (`409 Conflict`).\n"
            "- **Dead-Letter Queue (DLQ) Automática:** Payloads inválidos (`422`) ou com falha de assinatura (`401`) são registrados na tabela `dead_letter_webhooks`.\n"
            "- **Segurança Criptográfica:** Suporte a validação HMAC-SHA256 via header `X-Webhook-Signature`."
        ),
        openapi_tags=OPENAPI_TAGS_METADATA,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.state.config = config
    app.state.repository = repository

    def get_repo() -> WebhookEventRepository:
        return app.state.repository

    def get_cfg() -> APIGatewayConfig:
        return app.state.config

    @app.middleware("http")
    async def correlation_and_timing_middleware(
        request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        correlation_id = request.headers.get(
            "X-Correlation-ID", f"corr-{uuid.uuid4().hex[:12]}"
        )
        request.state.correlation_id = correlation_id
        t0 = time.perf_counter_ns()

        response: Response = await call_next(request)
        elapsed_ms = round((time.perf_counter_ns() - t0) / 1_000_000.0, 2)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", f"corr-{uuid.uuid4().hex[:12]}")
        raw_body = await request.body()
        raw_preview = raw_body.decode("utf-8", errors="replace") if raw_body else ""

        formatted_errors = []
        for err in exc.errors():
            loc_str = " -> ".join(str(part) for part in err.get("loc", []))
            formatted_errors.append(
                {
                    "field": loc_str,
                    "type": err.get("type", "validation_error"),
                    "message": err.get("msg", "Valor inválido"),
                }
            )

        summary_msg = f"Falha de validação de contrato Pydantic ({len(formatted_errors)} erro(s))."
        try:
            repository.record_dead_letter(
                endpoint=request.url.path,
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                error_code="SCHEMA_VALIDATION_FAILED",
                error_summary=f"{summary_msg} Campos: {[e['field'] for e in formatted_errors]}",
                raw_payload_preview=raw_preview,
            )
        except Exception as db_exc:
            logger.error("Erro ao gravar na Dead-Letter Queue: %s", db_exc)

        envelope = StandardErrorEnvelope(
            error_code="SCHEMA_VALIDATION_FAILED",
            message=summary_msg,
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            correlation_id=correlation_id,
            timestamp_utc=_utc_now_iso(),
            path=request.url.path,
            details=formatted_errors,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=envelope.model_dump(mode="json"),
        )

    @app.exception_handler(DuplicateWebhookEventError)
    async def duplicate_event_exception_handler(
        request: Request, exc: DuplicateWebhookEventError
    ) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", f"corr-{uuid.uuid4().hex[:12]}")
        envelope = StandardErrorEnvelope(
            error_code="DUPLICATE_EVENT_ID",
            message=str(exc),
            http_status=status.HTTP_409_CONFLICT,
            correlation_id=correlation_id,
            timestamp_utc=_utc_now_iso(),
            path=request.url.path,
            details=[{"event_id": exc.event_id, "resolution": "Idempotent rejection"}],
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=envelope.model_dump(mode="json"),
        )

    @app.exception_handler(WebhookEventNotFoundError)
    async def not_found_exception_handler(
        request: Request, exc: WebhookEventNotFoundError
    ) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", f"corr-{uuid.uuid4().hex[:12]}")
        envelope = StandardErrorEnvelope(
            error_code="EVENT_NOT_FOUND",
            message=str(exc),
            http_status=status.HTTP_404_NOT_FOUND,
            correlation_id=correlation_id,
            timestamp_utc=_utc_now_iso(),
            path=request.url.path,
            details=[{"event_id": exc.event_id}],
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=envelope.model_dump(mode="json"),
        )

    @app.exception_handler(WebhookAuthError)
    async def webhook_auth_exception_handler(
        request: Request, exc: WebhookAuthError
    ) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", f"corr-{uuid.uuid4().hex[:12]}")
        raw_body = await request.body()
        raw_preview = raw_body.decode("utf-8", errors="replace") if raw_body else ""

        repository.record_dead_letter(
            endpoint=request.url.path,
            http_status=status.HTTP_401_UNAUTHORIZED,
            error_code="INVALID_WEBHOOK_SIGNATURE",
            error_summary=str(exc),
            raw_payload_preview=raw_preview,
        )

        envelope = StandardErrorEnvelope(
            error_code="INVALID_WEBHOOK_SIGNATURE",
            message=str(exc),
            http_status=status.HTTP_401_UNAUTHORIZED,
            correlation_id=correlation_id,
            timestamp_utc=_utc_now_iso(),
            path=request.url.path,
            details=[{"header": "X-Webhook-Signature"}],
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=envelope.model_dump(mode="json"),
        )

    @app.get(
        "/health",
        tags=["1. Health & Diagnostics"],
        summary="Verifica integridade do API Gateway e conexão com o banco SQLite",
    )
    async def health_check(
        repo: WebhookEventRepository = Depends(get_repo),
        cfg: APIGatewayConfig = Depends(get_cfg),
    ) -> Dict[str, Any]:
        summary = repo.get_analytics_summary()
        return {
            "status": "HEALTHY",
            "service": cfg.api_title,
            "version": cfg.api_version,
            "database_engine": "SQLite3 (WAL Mode)",
            "total_events_persisted": summary.total_events_stored,
            "timestamp_utc": _utc_now_iso(),
        }

    @app.post(
        "/api/v1/webhooks/events",
        response_model=WebhookIngestResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["2. Webhook Ingestion"],
        summary="Recebe, valida e armazena um evento operacional via Webhook",
    )
    async def ingest_webhook_event(
        request: Request,
        payload: WebhookEventCreate,
        x_webhook_signature: Optional[str] = Header(default=None),
        repo: WebhookEventRepository = Depends(get_repo),
        cfg: APIGatewayConfig = Depends(get_cfg),
    ) -> WebhookIngestResponse:
        raw_body = await request.body()
        verify_webhook_signature(
            secret_key=cfg.webhook_secret_key,
            raw_body=raw_body,
            signature_header=x_webhook_signature,
            require_signature=cfg.require_hmac_signature,
        )
        result = repo.insert_event(payload)
        logger.info(
            "Webhook persistido | event_id=%s | service=%s | severity=%s | type=%s",
            payload.event_id,
            payload.service_name,
            payload.severity.value,
            payload.event_type.value,
        )
        return result

    @app.post(
        "/api/v1/webhooks/events/batch",
        response_model=BatchWebhookIngestResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["2. Webhook Ingestion"],
        summary="Ingestão transacional em lote (Bulk Webhook Ingestion) de até 100 eventos",
    )
    async def ingest_batch_webhook_events(
        batch: BatchWebhookCreate,
        repo: WebhookEventRepository = Depends(get_repo),
    ) -> BatchWebhookIngestResponse:
        result = repo.insert_batch_events(batch.events)
        logger.info(
            "Lote de Webhooks processado | recebidos=%d | inseridos=%d | duplicados_ignorados=%d",
            result.total_received,
            result.inserted_count,
            result.duplicate_skipped_count,
        )
        return result

    @app.get(
        "/api/v1/webhooks/events",
        response_model=PaginatedEventsResponse,
        tags=["3. Operational Logs Query"],
        summary="Lista e filtra eventos operacionais com suporte a paginação",
    )
    async def list_webhook_events(
        service_name: Optional[str] = Query(default=None),
        event_type: Optional[EventCategory] = Query(default=None),
        severity: Optional[LogSeverity] = Query(default=None),
        environment: Optional[EnvironmentType] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        repo: WebhookEventRepository = Depends(get_repo),
    ) -> PaginatedEventsResponse:
        return repo.query_events(
            service_name=service_name,
            event_type=event_type,
            severity=severity,
            environment=environment,
            limit=limit,
            offset=offset,
        )

    @app.get(
        "/api/v1/webhooks/events/{event_id}",
        response_model=StoredWebhookEvent,
        tags=["3. Operational Logs Query"],
        summary="Busca os detalhes completos de um evento operacional pelo seu `event_id`",
    )
    async def get_webhook_event(
        event_id: str,
        repo: WebhookEventRepository = Depends(get_repo),
    ) -> StoredWebhookEvent:
        return repo.get_event_by_id(event_id)

    @app.get(
        "/api/v1/analytics/summary",
        response_model=OperationalAnalyticsSummary,
        tags=["4. Observability & Dead-Letter Queue"],
        summary="Retorna agregações analíticas em tempo real sobre os logs operacionais e DLQ",
    )
    async def get_operational_analytics(
        repo: WebhookEventRepository = Depends(get_repo),
    ) -> OperationalAnalyticsSummary:
        return repo.get_analytics_summary()

    @app.get(
        "/api/v1/dead-letter-queue",
        response_model=List[DeadLetterItemResponse],
        tags=["4. Observability & Dead-Letter Queue"],
        summary="Lista os payloads rejeitados por falha de validação Pydantic (422) ou assinatura (401)",
    )
    async def list_dead_letter_queue(
        limit: int = Query(default=50, ge=1, le=200),
        repo: WebhookEventRepository = Depends(get_repo),
    ) -> List[DeadLetterItemResponse]:
        return repo.list_dead_letters(limit=limit)

    return app


app = create_app()
