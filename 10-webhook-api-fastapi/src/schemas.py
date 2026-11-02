"""
Schemas Rígidos Pydantic v2 para Validação de Webhooks e Respostas do API Gateway.

Utiliza `ConfigDict(extra="forbid", str_strip_whitespace=True)` para rejeitar campos
não documentados (Schema Drift Protection), validadores semânticos de IP, ISO-8601
e invariantes cruzadas de domínio (`@model_validator`).
"""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EVENT_ID_REGEX = re.compile(r"^EVT-[A-Za-z0-9_-]{4,64}$")
SERVICE_NAME_REGEX = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


class EventCategory(str, Enum):
    """Categorias oficiais de eventos operacionais aceitas pelo API Gateway."""

    DEPLOY_EVENT = "DEPLOY_EVENT"
    SECURITY_ALERT = "SECURITY_ALERT"
    DATABASE_METRIC = "DATABASE_METRIC"
    PAYMENT_GATEWAY_LOG = "PAYMENT_GATEWAY_LOG"
    DATA_PIPELINE_JOB = "DATA_PIPELINE_JOB"
    APPLICATION_ERROR = "APPLICATION_ERROR"


class LogSeverity(str, Enum):
    """Níveis padronizados de severidade operacional (Syslog / OpenTelemetry)."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EnvironmentType(str, Enum):
    """Ambientes de infraestrutura monitorados."""

    PRODUCTION = "PRODUCTION"
    STAGING = "STAGING"
    DEVELOPMENT = "DEVELOPMENT"


class TelemetryMetrics(BaseModel):
    """Métricas quantitativas de performance associadas ao evento de sistema."""

    model_config = ConfigDict(extra="forbid")

    latency_ms: float = Field(
        ...,
        ge=0.0,
        le=600_000.0,
        description="Tempo de execução/resposta da operação em milissegundos (0 a 600.000 ms).",
        examples=[42.8],
    )
    cpu_usage_pct: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Percentual de utilização de CPU da instância no momento do evento (0 a 100%).",
        examples=[64.5],
    )
    memory_mb: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1_048_576.0,
        description="Consumo de memória RAM em Megabytes.",
        examples=[512.0],
    )
    http_status_code: Optional[int] = Field(
        default=None,
        ge=100,
        le=599,
        description="Código HTTP associado à transação (100 a 599), quando aplicável.",
        examples=[200],
    )


class WebhookEventCreate(BaseModel):
    """
    Contrato de entrada (Webhook Payload) com validação estrita de tipos, formatos e regras de negócio.
    Campos extras não declarados no contrato são bloqueados (`extra='forbid'`).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "event_id": "EVT-20261102-9001",
                "event_type": "PAYMENT_GATEWAY_LOG",
                "severity": "INFO",
                "environment": "PRODUCTION",
                "service_name": "pix-settlement-worker",
                "host_ip": "10.24.18.105",
                "trace_id": "trc-8f92a1c4b7e01923",
                "event_timestamp_utc": "2026-11-02T09:50:15.120Z",
                "message": "Liquidação de transação PIX processada com sucesso no SPI.",
                "metrics": {
                    "latency_ms": 38.4,
                    "cpu_usage_pct": 41.2,
                    "memory_mb": 384.0,
                    "http_status_code": 200,
                },
                "tags": ["pix", "spi", "settlement"],
                "payload_context": {
                    "bank_ispb": "18236120",
                    "tx_count": 1,
                },
            }
        },
    )

    event_id: str = Field(
        ...,
        description="Identificador único global do evento no padrão 'EVT-<id>'.",
        examples=["EVT-20261102-9001"],
    )
    event_type: EventCategory = Field(
        ...,
        description="Categoria semântica do evento operacional.",
    )
    severity: LogSeverity = Field(
        ...,
        description="Severidade operacional do log.",
    )
    environment: EnvironmentType = Field(
        default=EnvironmentType.PRODUCTION,
        description="Ambiente de origem do serviço emissor.",
    )
    service_name: str = Field(
        ...,
        description="Nome canônico do microsserviço emissor (letras minúsculas, números e hífens).",
        examples=["pix-settlement-worker"],
    )
    host_ip: str = Field(
        ...,
        description="Endereço IPv4 ou IPv6 válido do host ou pod Kubernetes de origem.",
        examples=["10.24.18.105"],
    )
    trace_id: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=64,
        description="Identificador de rastreamento distribuído (OpenTelemetry Trace ID). Obrigatório para eventos CRITICAL ou SECURITY_ALERT.",
        examples=["trc-8f92a1c4b7e01923"],
    )
    event_timestamp_utc: str = Field(
        ...,
        description="Timestamp ISO-8601 em UTC da ocorrência do evento na origem.",
        examples=["2026-11-02T09:50:15.120Z"],
    )
    message: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Descrição legível detalhando o evento operacional.",
    )
    metrics: TelemetryMetrics = Field(
        ...,
        description="Objeto estruturado de métricas de telemetria.",
    )
    tags: List[str] = Field(
        default_factory=list,
        max_length=20,
        description="Lista de tags de indexação operacional.",
    )
    payload_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados estruturados de domínio específicos do evento.",
    )

    @field_validator("event_id")
    @classmethod
    def validate_event_id_format(cls, value: str) -> str:
        if not EVENT_ID_REGEX.match(value):
            raise ValueError(
                "O campo 'event_id' deve seguir o padrão 'EVT-<alfanumerico>' (mín. 4 caracteres após 'EVT-')."
            )
        return value

    @field_validator("service_name")
    @classmethod
    def validate_service_name_slug(cls, value: str) -> str:
        if not SERVICE_NAME_REGEX.match(value):
            raise ValueError(
                "O campo 'service_name' deve estar em kebab-case/snake_case minúsculo (ex: 'order-api-service')."
            )
        return value

    @field_validator("host_ip")
    @classmethod
    def validate_ip_address(cls, value: str) -> str:
        try:
            ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError(f"Endereço IP inválido em 'host_ip': '{value}'.") from exc
        return value

    @field_validator("event_timestamp_utc")
    @classmethod
    def validate_iso_timestamp(cls, value: str) -> str:
        normalized = value.replace("Z", "+00:00")
        try:
            datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Timestamp '{value}' inválido. Utilize o formato ISO-8601 (ex: '2026-11-02T09:50:15Z')."
            ) from exc
        return value

    @model_validator(mode="after")
    def validate_critical_and_security_invariants(self) -> WebhookEventCreate:
        if (
            self.severity == LogSeverity.CRITICAL
            or self.event_type == EventCategory.SECURITY_ALERT
        ) and not self.trace_id:
            raise ValueError(
                "Eventos com severidade 'CRITICAL' ou categoria 'SECURITY_ALERT' exigem obrigatoriamente 'trace_id' preenchido para auditoria forense."
            )
        return self


class BatchWebhookCreate(BaseModel):
    """Contrato para ingestão em lote (Bulk Webhook Ingestion) de até 100 eventos."""

    model_config = ConfigDict(extra="forbid")

    events: List[WebhookEventCreate] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Lista de eventos de webhook a serem persistidos transacionalmente.",
    )


class WebhookIngestResponse(BaseModel):
    """Resposta padronizada de confirmação de recebimento e persistência do Webhook."""

    status: str = "ACCEPTED"
    event_id: str
    service_name: str
    severity: LogSeverity
    received_at_utc: str
    payload_sha256: str


class BatchWebhookIngestResponse(BaseModel):
    """Resposta para processamento de lote de Webhooks."""

    status: str = "BATCH_PROCESSED"
    total_received: int
    inserted_count: int
    duplicate_skipped_count: int
    processed_at_utc: str
    inserted_event_ids: List[str]


class StoredWebhookEvent(BaseModel):
    """Representação completa de um evento persistido no banco de dados relacional."""

    event_id: str
    event_type: EventCategory
    severity: LogSeverity
    environment: EnvironmentType
    service_name: str
    host_ip: str
    trace_id: Optional[str]
    event_timestamp_utc: str
    received_at_utc: str
    message: str
    metrics: TelemetryMetrics
    tags: List[str]
    payload_context: Dict[str, Any]
    payload_sha256: str


class PaginatedEventsResponse(BaseModel):
    """Envelope de listagem paginada de logs operacionais."""

    total_matching: int
    limit: int
    offset: int
    items: List[StoredWebhookEvent]


class OperationalAnalyticsSummary(BaseModel):
    """Métricas agregadas de observabilidade dos logs operacionais armazenados."""

    total_events_stored: int
    total_dead_letter_rejections: int
    avg_latency_ms: float
    max_latency_ms: float
    avg_cpu_usage_pct: float
    events_by_severity: Dict[str, int]
    events_by_category: Dict[str, int]
    events_by_environment: Dict[str, int]
    top_services: List[Dict[str, Any]]


class DeadLetterItemResponse(BaseModel):
    """Registro de auditoria de um payload inválido ou rejeitado (Dead-Letter Queue)."""

    dlq_id: int
    received_at_utc: str
    endpoint: str
    http_status: int
    error_code: str
    error_summary: str
    raw_payload_preview: str


class StandardErrorEnvelope(BaseModel):
    """Envelope padronizado de erro (inspirado na RFC 7807 Problem Details for HTTP APIs)."""

    error_code: str
    message: str
    http_status: int
    correlation_id: str
    timestamp_utc: str
    path: str
    details: List[Dict[str, Any]] = Field(default_factory=list)
