"""
Simulador de Tráfego de Webhooks Operacionais (Demo Runner).

Envia eventos de microsserviços (unitários, em lote e payloads malformados para teste de DLQ)
para o FastAPI Gateway, popula o banco SQLite relacional `operational_logs_gateway.db`
e gera um relatório de observabilidade em `reports/gateway_operational_report.md`.
"""

from __future__ import annotations

import shutil
from fastapi.testclient import TestClient

from src.config import APIGatewayConfig, setup_logger
from src.main import create_app

logger = setup_logger("Gateway-Demo-Runner")


def run_demo_simulation(clean_start: bool = True) -> None:
    config = APIGatewayConfig()
    if clean_start and config.data_dir.exists():
        shutil.rmtree(config.data_dir)
    config.ensure_directories()

    app = create_app(custom_config=config)
    client = TestClient(app)

    logger.info("=" * 88)
    logger.info("SIMULANDO TRÁFEGO DE WEBHOOKS OPERACIONAIS NO FASTAPI GATEWAY")
    logger.info("=" * 88)

    sample_events = [
        {
            "event_id": "EVT-20261102-1001",
            "event_type": "PAYMENT_GATEWAY_LOG",
            "severity": "INFO",
            "environment": "PRODUCTION",
            "service_name": "pix-settlement-worker",
            "host_ip": "10.24.18.105",
            "trace_id": "trc-8f92a1c4b7e01923",
            "event_timestamp_utc": "2026-11-02T09:40:10Z",
            "message": "Liquidação de transação PIX processada com sucesso no SPI.",
            "metrics": {"latency_ms": 34.2, "cpu_usage_pct": 38.0, "memory_mb": 412.0, "http_status_code": 200},
            "tags": ["pix", "settlement"],
            "payload_context": {"bank_ispb": "18236120"},
        },
        {
            "event_id": "EVT-20261102-1002",
            "event_type": "DATABASE_METRIC",
            "severity": "WARNING",
            "environment": "PRODUCTION",
            "service_name": "postgres-rds-monitor",
            "host_ip": "10.24.20.12",
            "trace_id": "trc-1290ab44cc918271",
            "event_timestamp_utc": "2026-11-02T09:42:00Z",
            "message": "Pool de conexões PgBouncer atingiu 82% da capacidade máxima.",
            "metrics": {"latency_ms": 148.5, "cpu_usage_pct": 78.4, "memory_mb": 6144.0, "http_status_code": 200},
            "tags": ["postgres", "connection-pool"],
            "payload_context": {"active_connections": 164, "max_connections": 200},
        },
        {
            "event_id": "EVT-20261102-1003",
            "event_type": "SECURITY_ALERT",
            "severity": "CRITICAL",
            "environment": "PRODUCTION",
            "service_name": "waf-edge-shield",
            "host_ip": "172.16.0.44",
            "trace_id": "trc-sec-998877665544",
            "event_timestamp_utc": "2026-11-02T09:45:30Z",
            "message": "Bloqueio de rajada de tentativas de Credential Stuffing no endpoint /oauth/token.",
            "metrics": {"latency_ms": 12.1, "cpu_usage_pct": 52.0, "memory_mb": 1024.0, "http_status_code": 429},
            "tags": ["waf", "security", "rate-limit"],
            "payload_context": {"blocked_ip": "198.51.100.77", "attempts_1m": 450},
        },
        {
            "event_id": "EVT-20261102-1004",
            "event_type": "DATA_PIPELINE_JOB",
            "severity": "INFO",
            "environment": "PRODUCTION",
            "service_name": "spark-silver-compactor",
            "host_ip": "10.24.90.15",
            "trace_id": "trc-spark-7712389123",
            "event_timestamp_utc": "2026-11-02T09:48:00Z",
            "message": "Job de compactação de partições Parquet finalizado na Camada Silver.",
            "metrics": {"latency_ms": 1420.0, "cpu_usage_pct": 88.5, "memory_mb": 16384.0, "http_status_code": 200},
            "tags": ["spark", "parquet", "lakehouse"],
            "payload_context": {"files_compacted": 48, "rows_processed": 1250000},
        },
        {
            "event_id": "EVT-20261102-1005",
            "event_type": "APPLICATION_ERROR",
            "severity": "ERROR",
            "environment": "STAGING",
            "service_name": "checkout-orchestrator-api",
            "host_ip": "10.25.10.99",
            "trace_id": "trc-err-55123981239",
            "event_timestamp_utc": "2026-11-02T09:50:00Z",
            "message": "Timeout ao consultar serviço externo de cálculo de frete.",
            "metrics": {"latency_ms": 3012.4, "cpu_usage_pct": 33.1, "memory_mb": 512.0, "http_status_code": 504},
            "tags": ["checkout", "shipping-timeout"],
            "payload_context": {"carrier": "correios-sedex", "retry_attempt": 3},
        },
    ]

    for ev in sample_events:
        res = client.post("/api/v1/webhooks/events", json=ev)
        logger.info("POST /api/v1/webhooks/events -> %d | event_id=%s", res.status_code, ev["event_id"])

    invalid_payload = {
        "event_id": "EVT-MALFORMED-999",
        "event_type": "SECURITY_ALERT",
        "severity": "CRITICAL",
        "environment": "PRODUCTION",
        "service_name": "INVALID SERVICE NAME WITH SPACES",
        "host_ip": "999.999.999.999",
        "trace_id": None,
        "event_timestamp_utc": "DATA_INVALIDA",
        "message": "Payload corrompido para teste de Dead-Letter Queue.",
        "metrics": {"latency_ms": -50.0},
    }
    bad_res = client.post("/api/v1/webhooks/events", json=invalid_payload)
    logger.warning(
        "POST /api/v1/webhooks/events (Payload Inválido) -> %d | Registrado na Dead-Letter Queue",
        bad_res.status_code,
    )

    summary = client.get("/api/v1/analytics/summary").json()
    dlq_list = client.get("/api/v1/dead-letter-queue").json()

    report_path = config.reports_dir / "gateway_operational_report.md"
    lines = [
        "# Relatório Operacional — FastAPI Webhook & Logs Gateway",
        "",
        f"- **Eventos Válidos Persistidos:** `{summary['total_events_stored']}`",
        f"- **Payloads Inválidos Bloqueados (Dead-Letter Queue):** `{summary['total_dead_letter_rejections']}`",
        f"- **Latência Média Registrada:** `{summary['avg_latency_ms']} ms` (Máx: `{summary['max_latency_ms']} ms`)",
        f"- **Uso Médio de CPU:** `{summary['avg_cpu_usage_pct']}%`",
        "",
        "## Distribuição por Severidade",
        "",
        "| Severidade | Total de Eventos |",
        "| :--- | :---: |",
    ]
    for sev, cnt in summary["events_by_severity"].items():
        lines.append(f"| `{sev}` | {cnt} |")

    lines.extend(
        [
            "",
            "## Registros na Dead-Letter Queue (Payloads Rejeitados pelo Pydantic)",
            "",
            "| DLQ ID | Horário (UTC) | Endpoint | HTTP Status | Código de Erro | Diagnóstico |",
            "| :---: | :---: | :---: | :---: | :---: | :--- |",
        ]
    )
    for item in dlq_list:
        lines.append(
            f"| `{item['dlq_id']}` | `{item['received_at_utc']}` | `{item['endpoint']}` | "
            f"`{item['http_status']}` | `{item['error_code']}` | {item['error_summary']} |"
        )

    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Relatório operacional salvo em: %s", report_path)


if __name__ == "__main__":
    run_demo_simulation()
