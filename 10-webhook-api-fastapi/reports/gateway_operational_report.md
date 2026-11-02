# Relatório Operacional — FastAPI Webhook & Logs Gateway

- **Eventos Válidos Persistidos:** `5`
- **Payloads Inválidos Bloqueados (Dead-Letter Queue):** `1`
- **Latência Média Registrada:** `925.44 ms` (Máx: `3012.4 ms`)
- **Uso Médio de CPU:** `58.0%`

## Distribuição por Severidade

| Severidade | Total de Eventos |
| :--- | :---: |
| `CRITICAL` | 1 |
| `ERROR` | 1 |
| `INFO` | 2 |
| `WARNING` | 1 |

## Registros na Dead-Letter Queue (Payloads Rejeitados pelo Pydantic)

| DLQ ID | Horário (UTC) | Endpoint | HTTP Status | Código de Erro | Diagnóstico |
| :---: | :---: | :---: | :---: | :---: | :--- |
| `1` | `2026-11-02T10:18:47.575Z` | `/api/v1/webhooks/events` | `422` | `SCHEMA_VALIDATION_FAILED` | Falha de validação de contrato Pydantic (4 erro(s)). Campos: ['body -> service_name', 'body -> host_ip', 'body -> event_timestamp_utc', 'body -> metrics -> latency_ms'] |
