"""Suíte de Testes Unitários e de Integração com pytest para o FastAPI Webhook Gateway."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import APIGatewayConfig
from src.main import create_app
from src.security import compute_hmac_sha256


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    """Instancia o FastAPI TestClient acoplado a um banco SQLite temporário isolado."""
    test_cfg = APIGatewayConfig(
        base_dir=tmp_path,
        webhook_secret_key="test_secret_hmac_key_2026",
        require_hmac_signature=False,
    )
    app = create_app(custom_config=test_cfg)
    return TestClient(app)


def _sample_valid_payload(event_id: str = "EVT-20261102-0001") -> Dict[str, Any]:
    return {
        "event_id": event_id,
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
        "payload_context": {"bank_ispb": "18236120", "tx_count": 1},
    }


def test_01_health_check_and_interactive_swagger_docs(client: TestClient) -> None:
    """Valida endpoint /health e disponibilidade automática do Swagger UI (/docs) e OpenAPI."""
    health_res = client.get("/health")
    assert health_res.status_code == 200
    body = health_res.json()
    assert body["status"] == "HEALTHY"
    assert body["total_events_persisted"] == 0
    assert "X-Correlation-ID" in health_res.headers
    assert "X-Process-Time-Ms" in health_res.headers

    docs_res = client.get("/docs")
    assert docs_res.status_code == 200
    assert "Swagger UI" in docs_res.text

    openapi_res = client.get("/openapi.json")
    assert openapi_res.status_code == 200
    assert "/api/v1/webhooks/events" in openapi_res.json()["paths"]


def test_02_ingest_valid_webhook_and_get_by_id(client: TestClient) -> None:
    """Valida ingestão de um Webhook válido (201 Created) e recuperação por ID (200 OK)."""
    payload = _sample_valid_payload("EVT-20261102-1001")
    post_res = client.post("/api/v1/webhooks/events", json=payload)
    assert post_res.status_code == 201
    ingest_data = post_res.json()
    assert ingest_data["status"] == "ACCEPTED"
    assert ingest_data["event_id"] == "EVT-20261102-1001"
    assert len(ingest_data["payload_sha256"]) == 64

    get_res = client.get("/api/v1/webhooks/events/EVT-20261102-1001")
    assert get_res.status_code == 200
    stored = get_res.json()
    assert stored["service_name"] == "pix-settlement-worker"
    assert stored["metrics"]["latency_ms"] == 38.4

    missing_res = client.get("/api/v1/webhooks/events/EVT-INEXISTENTE")
    assert missing_res.status_code == 404
    assert missing_res.json()["error_code"] == "EVENT_NOT_FOUND"


def test_03_duplicate_event_id_returns_409_conflict(client: TestClient) -> None:
    """Garante proteção de idempotência ao receber um event_id repetido (409 Conflict)."""
    payload = _sample_valid_payload("EVT-DUP-9999")
    first = client.post("/api/v1/webhooks/events", json=payload)
    assert first.status_code == 201

    second = client.post("/api/v1/webhooks/events", json=payload)
    assert second.status_code == 409
    err_body = second.json()
    assert err_body["error_code"] == "DUPLICATE_EVENT_ID"


def test_04_strict_pydantic_validation_and_dead_letter_queue(client: TestClient) -> None:
    """
    Testa rejeição de payloads inválidos (422 Unprocessable Entity) e gravação na DLQ.
    """
    p_extra = _sample_valid_payload("EVT-ERR-0001")
    p_extra["hacker_injected_field"] = "drop table"
    res1 = client.post("/api/v1/webhooks/events", json=p_extra)
    assert res1.status_code == 422
    assert res1.json()["error_code"] == "SCHEMA_VALIDATION_FAILED"

    p_ip = _sample_valid_payload("EVT-ERR-0002")
    p_ip["host_ip"] = "999.888.777.666"
    res2 = client.post("/api/v1/webhooks/events", json=p_ip)
    assert res2.status_code == 422

    p_lat = _sample_valid_payload("EVT-ERR-0003")
    p_lat["metrics"]["latency_ms"] = -25.0
    res3 = client.post("/api/v1/webhooks/events", json=p_lat)
    assert res3.status_code == 422

    p_crit = _sample_valid_payload("EVT-ERR-0004")
    p_crit["severity"] = "CRITICAL"
    p_crit["trace_id"] = None
    res4 = client.post("/api/v1/webhooks/events", json=p_crit)
    assert res4.status_code == 422

    dlq_res = client.get("/api/v1/dead-letter-queue")
    assert dlq_res.status_code == 200
    dlq_items = dlq_res.json()
    assert len(dlq_items) == 4


def test_05_hmac_sha256_signature_validation(client: TestClient) -> None:
    """Valida aceitação de assinatura HMAC legítima (201) e bloqueio de assinatura adulterada (401)."""
    payload = _sample_valid_payload("EVT-HMAC-0001")
    raw_bytes = json.dumps(payload).encode("utf-8")
    valid_sig = compute_hmac_sha256("test_secret_hmac_key_2026", raw_bytes)

    ok_res = client.post(
        "/api/v1/webhooks/events",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": valid_sig},
    )
    assert ok_res.status_code == 201

    bad_res = client.post(
        "/api/v1/webhooks/events",
        json=_sample_valid_payload("EVT-HMAC-0002"),
        headers={"X-Webhook-Signature": "sha256=00000000000000000000000000000000"},
    )
    assert bad_res.status_code == 401
    assert bad_res.json()["error_code"] == "INVALID_WEBHOOK_SIGNATURE"


def test_06_batch_ingestion_filtering_and_analytics(client: TestClient) -> None:
    """Testa ingestão em lote (/batch), filtros de consulta e sumário analítico (/analytics/summary)."""
    e1 = _sample_valid_payload("EVT-BATCH-001")
    e2 = _sample_valid_payload("EVT-BATCH-002")
    e2["severity"] = "ERROR"
    e2["event_type"] = "DATABASE_METRIC"
    e2["service_name"] = "postgres-replica-monitor"
    e2["metrics"]["latency_ms"] = 840.0

    batch_res = client.post("/api/v1/webhooks/events/batch", json={"events": [e1, e2]})
    assert batch_res.status_code == 201
    assert batch_res.json()["inserted_count"] == 2

    filter_res = client.get("/api/v1/webhooks/events?severity=ERROR")
    assert filter_res.status_code == 200
    filtered = filter_res.json()
    assert filtered["total_matching"] == 1
    assert filtered["items"][0]["event_id"] == "EVT-BATCH-002"

    analytics_res = client.get("/api/v1/analytics/summary")
    assert analytics_res.status_code == 200
    summary = analytics_res.json()
    assert summary["total_events_stored"] == 2
    assert summary["events_by_severity"]["ERROR"] == 1
    assert summary["max_latency_ms"] == 840.0
