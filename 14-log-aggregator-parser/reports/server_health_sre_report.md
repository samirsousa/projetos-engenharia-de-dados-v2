# Relatório Analítico SRE: Saúde do Servidor, Agregação de Logs & Segurança

## 1. Sumário Executivo dos Quatro Sinais de Ouro (SRE Golden Signals)

| Métrica SRE / Observabilidade | Valor Consolidado | Meta / Diagnóstico |
| :--- | ---: | :--- |
| **Total de Linhas de Log Processadas** | `3,200` | Stream centralizado do cluster |
| **Eventos Estruturados via Regex** | `3,190` | Taxa de sucesso de `99.69%` |
| **Linhas Malformadas em Quarentena (DLQ)** | `10` | Isoladas sem interrupção do parser |
| **Disponibilidade Global (Non-5xx SLO)** | **`89.81%`** | Meta SLO `>= 98.50%` |
| **Requisições com Sucesso (`2xx` / `HTTP 200`)** | `2,221` (`1,573` HTTP 200) | Tráfego saudável atendido |
| **Erros de Cliente (`4xx` / `HTTP 404`)** | `644` (`504` HTTP 404) | Taxa 4xx: `20.19%` |
| **Erros Críticos de Servidor (`5xx` / `HTTP 500`)** | `325` (`201` HTTP 500) | Taxa 5xx: `10.19%` |
| **Latência Média / P95 / P99** | `175.90 ms` / `1211.78 ms` / `1978.84 ms` | Perfil de tempo de resposta |
| **Índice Global Apdex ($T = 120\text{ ms}$)** | **`0.8434`** | Satisfação de tempo de resposta |
| **Tentativas de Ataque Detectadas via Regex** | `282` | SQLi, Path Traversal, Brute-Force & Scans |
| **Volume de Tráfego Egresso** | `7.29 MB` | Banda total consumida |

---

## 2. Agregação por Código de Status HTTP (`agg_metrics_by_status_code`)

| Status Code | Classe HTTP | Descrição Técnica | Ocorrências | % Tráfego | Latência Média (ms) | Latência Máx (ms) | IPs Distintos | Rota Mais Afetada |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| **`200`** | `2xx Success` | OK - Requisição processada com sucesso | **1,573** | `49.31%` | 57.17 | 209.86 | 10 | `/api/v1/payments/authorize` |
| **`404`** | `4xx Client Error` | Not Found - Rota ou recurso inexistente | **504** | `15.80%` | 23.19 | 43.12 | 12 | `/api/v1/catalog/products/{id}` |
| **`201`** | `2xx Success` | Created - Recurso criado com sucesso | **327** | `10.25%` | 107.30 | 164.81 | 10 | `/api/v1/orders/{id}/checkout` |
| **`204`** | `2xx Success` | No Content - Processado sem corpo de resposta | **321** | `10.06%` | 19.86 | 31.98 | 10 | `/api/v1/sessions/{id}` |
| **`500`** | `5xx Server Error` | Internal Server Error - Exceção não tratada no backend | **201** | `6.30%` | 968.69 | 1748.86 | 12 | `/api/v1/ledger/reconcile` |
| **`403`** | `4xx Client Error` | Forbidden - Acesso negado pelo WAF / RBAC | **57** | `1.79%` | 25.01 | 43.77 | 4 | `/[SECURITY_PATH_TRAVERSAL_PROBE]` |
| **`503`** | `5xx Server Error` | Service Unavailable - Sobrecarga de pool de conexões | **48** | `1.50%` | 1085.16 | 1672.12 | 8 | `/api/v1/orders/{id}/details` |
| **`502`** | `5xx Server Error` | Bad Gateway - Falha de comunicação com upstream | **43** | `1.35%` | 1141.69 | 1740.94 | 8 | `/api/v1/orders/{id}/details` |
| **`401`** | `4xx Client Error` | Unauthorized - Falha de autenticação / Token inválido | **33** | `1.03%` | 24.98 | 43.17 | 4 | `/api/v1/auth/login` |
| **`504`** | `5xx Server Error` | Gateway Timeout - Timeout de banco de dados / upstream | **33** | `1.03%` | 3595.15 | 4856.57 | 8 | `/api/v1/payments/authorize` |
| **`429`** | `4xx Client Error` | Too Many Requests - Rate Limit excedido | **27** | `0.85%` | 25.55 | 43.07 | 4 | `/api/v1/auth/login` |
| **`400`** | `4xx Client Error` | Bad Request - Payload ou query inválida | **23** | `0.72%` | 24.80 | 43.78 | 4 | `/api/v1/catalog/products/{id}` |

---

## 3. Agregação por Rota Normalizada (`agg_metrics_by_route`)

| Verbo | Rota Canônica Normalizada (Regex) | Hits | HTTP 200 | HTTP 404 | HTTP 500 | Taxa 4xx % | Taxa 5xx % | Latência Média (ms) | P95 (ms) | Apdex | Status de Saúde |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| `GET` | `/api/v1/orders/{id}/details` | 404 | 313 | 0 | 0 | `0.0%` | **`22.5%`** | 293.9 | 1456.1 | `0.775` | `CRITICAL_DEGRADATION` |
| `POST` | `/api/v1/ledger/reconcile` | 72 | 0 | 0 | 62 | `0.0%` | **`100.0%`** | 1433.8 | 3816.6 | `0.000` | `CRITICAL_DEGRADATION` |
| `POST` | `/api/v1/payments/authorize` | 408 | 343 | 0 | 50 | `0.0%` | **`15.9%`** | 391.8 | 1594.6 | `0.592` | `CRITICAL_DEGRADATION` |
| `POST` | `/api/v1/orders/{id}/checkout` | 392 | 0 | 0 | 57 | `0.0%` | **`16.6%`** | 334.0 | 1473.2 | `0.648` | `CRITICAL_DEGRADATION` |
| `GET` | `/api/v1/catalog/products/{id}` | 483 | 298 | 109 | 32 | `31.7%` | **`6.6%`** | 33.8 | 64.5 | `0.934` | `WARNING_LATENCY_SLO` |
| `DELETE` | `/api/v1/sessions/{id}` | 321 | 0 | 0 | 0 | `0.0%` | **`0.0%`** | 19.9 | 30.4 | `1.000` | `HEALTHY_OPTIMAL` |
| `GET` | `/healthz` | 314 | 314 | 0 | 0 | `0.0%` | **`0.0%`** | 3.9 | 6.2 | `1.000` | `HEALTHY_OPTIMAL` |
| `GET` | `/api/v1/users/{uuid}/profile` | 305 | 305 | 0 | 0 | `0.0%` | **`0.0%`** | 41.8 | 69.0 | `1.000` | `HEALTHY_OPTIMAL` |
| `GET` | `/api/v1/legacy/reports/export` | 107 | 0 | 107 | 0 | `100.0%` | **`0.0%`** | 22.8 | 34.6 | `1.000` | `HIGH_CLIENT_ERROR_OR_SCAN` |
| `GET` | `/assets/icons/favicon-old.ico` | 95 | 0 | 95 | 0 | `100.0%` | **`0.0%`** | 22.1 | 34.6 | `1.000` | `HIGH_CLIENT_ERROR_OR_SCAN` |
| `GET` | `/api/v1/orders/{id}/invoice.pdf` | 83 | 0 | 83 | 0 | `100.0%` | **`0.0%`** | 22.7 | 35.0 | `1.000` | `HIGH_CLIENT_ERROR_OR_SCAN` |
| `GET` | `/[SECURITY_PATH_TRAVERSAL_PROBE]` | 75 | 0 | 39 | 0 | `100.0%` | **`0.0%`** | 26.0 | 42.4 | `1.000` | `HIGH_CLIENT_ERROR_OR_SCAN` |
| `POST` | `/api/v1/auth/login` | 60 | 0 | 0 | 0 | `100.0%` | **`0.0%`** | 25.2 | 40.9 | `1.000` | `HIGH_CLIENT_ERROR_OR_SCAN` |
| `GET` | `/.git/config` | 27 | 0 | 27 | 0 | `100.0%` | **`0.0%`** | 25.6 | 40.9 | `1.000` | `HIGH_CLIENT_ERROR_OR_SCAN` |
| `GET` | `/.env` | 18 | 0 | 18 | 0 | `100.0%` | **`0.0%`** | 21.9 | 36.5 | `1.000` | `HIGH_CLIENT_ERROR_OR_SCAN` |
| `GET` | `/phpmyadmin/index.php` | 18 | 0 | 18 | 0 | `100.0%` | **`0.0%`** | 27.7 | 40.3 | `1.000` | `HIGH_CLIENT_ERROR_OR_SCAN` |
| `GET` | `/wp-admin/setup-config.php` | 8 | 0 | 8 | 0 | `100.0%` | **`0.0%`** | 26.8 | 40.2 | `1.000` | `HIGH_CLIENT_ERROR_OR_SCAN` |

---

## 4. Agregação por Endereço IP Cliente & Reputação WAF (`agg_metrics_by_ip`)

| Endereço IP | Escopo | Requisições | 2xx | HTTP 404 | HTTP 500 | Taxa de Erro % | Banda (KB) | Latência Média (ms) | Hits de Ataque | Vetor de Ameaça Predominante | Reputação / Ação WAF |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | :--- |
| `185.220.101.44` | `EXTERNAL_PUBLIC` | 78 | 0 | 29 | 7 | `100.0%` | 26.5 | 24.8 | **`78`** | `PATH_TRAVERSAL_ATTEMPT` | **`MALICIOUS_BLOCK_WAF`** |
| `203.0.113.195` | `EXTERNAL_PUBLIC` | 107 | 0 | 65 | 9 | `100.0%` | 33.2 | 24.3 | **`72`** | `PATH_TRAVERSAL_ATTEMPT` | **`MALICIOUS_BLOCK_WAF`** |
| `198.51.100.77` | `EXTERNAL_PUBLIC` | 69 | 0 | 24 | 10 | `100.0%` | 22.9 | 25.1 | **`69`** | `SQL_INJECTION_ATTEMPT` | **`MALICIOUS_BLOCK_WAF`** |
| `45.155.205.109` | `EXTERNAL_PUBLIC` | 63 | 0 | 27 | 6 | `100.0%` | 19.6 | 25.1 | **`63`** | `SQL_INJECTION_ATTEMPT` | **`MALICIOUS_BLOCK_WAF`** |
| `189.40.22.108` | `EXTERNAL_PUBLIC` | 324 | 240 | 49 | 17 | `25.9%` | 853.0 | 205.5 | **`0`** | `NONE` | **`TRUSTED_CLIENT`** |
| `187.12.90.33` | `EXTERNAL_PUBLIC` | 321 | 231 | 54 | 21 | `28.0%` | 867.7 | 174.5 | **`0`** | `NONE` | **`TRUSTED_CLIENT`** |
| `191.252.60.12` | `EXTERNAL_PUBLIC` | 319 | 239 | 44 | 26 | `25.1%` | 697.3 | 217.8 | **`0`** | `NONE` | **`TRUSTED_CLIENT`** |
| `200.155.80.42` | `EXTERNAL_PUBLIC` | 309 | 238 | 42 | 18 | `23.0%` | 776.8 | 187.2 | **`0`** | `NONE` | **`TRUSTED_CLIENT`** |
| `201.68.14.99` | `EXTERNAL_PUBLIC` | 306 | 203 | 56 | 26 | `33.7%` | 686.9 | 255.9 | **`0`** | `NONE` | **`SUSPICIOUS_RATE_LIMIT`** |
| `170.238.11.74` | `EXTERNAL_PUBLIC` | 288 | 216 | 36 | 18 | `25.0%` | 643.7 | 217.3 | **`0`** | `NONE` | **`TRUSTED_CLIENT`** |
| `177.84.120.15` | `EXTERNAL_PUBLIC` | 280 | 205 | 36 | 24 | `26.8%` | 635.8 | 263.8 | **`0`** | `NONE` | **`TRUSTED_CLIENT`** |
| `179.110.45.201` | `EXTERNAL_PUBLIC` | 252 | 175 | 42 | 19 | `30.6%` | 599.2 | 242.9 | **`0`** | `NONE` | **`SUSPICIOUS_RATE_LIMIT`** |
| `192.168.10.50` | `INTERNAL_RFC1918` | 239 | 239 | 0 | 0 | `0.0%` | 845.6 | 57.2 | **`0`** | `NONE` | **`TRUSTED_CLIENT`** |
| `10.240.0.10` | `INTERNAL_RFC1918` | 235 | 235 | 0 | 0 | `0.0%` | 757.0 | 58.3 | **`0`** | `NONE` | **`TRUSTED_CLIENT`** |

---

## 5. Saúde Operacional por Nó do Cluster (`agg_metrics_by_node`)

| Node ID | Total Hits | Sucesso 2xx | Erros 4xx | Erros 5xx | Disponibilidade SLO % | Latência Média (ms) | P95 (ms) | Apdex | Status do Nó |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| `app-worker-01` | 799 | 561 | 163 | 75 | **`90.61%`** | 175.10 | 1123.49 | `0.8467` | `SLO_BREACH_INVESTIGATE` |
| `app-worker-02` | 849 | 584 | 172 | 93 | **`89.05%`** | 177.57 | 1296.48 | `0.8398` | `SLO_BREACH_INVESTIGATE` |
| `edge-ingress-01` | 781 | 536 | 162 | 83 | **`89.37%`** | 163.45 | 1069.63 | `0.8412` | `SLO_BREACH_INVESTIGATE` |
| `edge-ingress-02` | 761 | 540 | 147 | 74 | **`90.28%`** | 187.65 | 1257.26 | `0.8463` | `SLO_BREACH_INVESTIGATE` |