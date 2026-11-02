# Relatório Diário de Auditoria de Dados — Pipeline CDC (Camada Silver)

- **Data de Referência:** `2026-11-02`
- **Gerado em (UTC):** `2026-11-02T02:04:28.962Z`
- **Pipeline:** `SQLite-Debezium-Silver-CDC v1.0.0`
- **Status de Reconciliação OLTP vs Silver:** **CONFORME (ZERO DRIFT)**

---

## 1. Reconciliação de Estado e Paridade Criptográfica (OLTP vs Silver)

| Métrica de Qualidade / Paridade | Origem OLTP (`orders`) | Espelho Silver (`vw_silver_orders_active`) | Divergência (Drift) |
| :--- | :---: | :---: | :---: |
| **Registros Ativos** | `32` | `32` | `0` |
| **Registros Deletados (Tombstones Silver)** | `N/A (Hard Delete)` | `8` | `Governado via _is_deleted=1` |
| **Volume Financeiro Ativo (GMV)** | `R$ 197,189.70` | `R$ 197,189.70` | `R$ 0.00` |
| **Hash SHA-256 do Conjunto Ativo** | `b3b6a9aef87dae9b...` | `b3b6a9aef87dae9b...` | `MATCH EXATO` |

---

## 2. Volumetria de Eventos CDC e Telemetria de Replicação

- **Lotes JSON Processados no Dia:** `6`
- **Faixa de LSN (Log Sequence Number):** `1 -> 60`
- **Total de Eventos Auditados:** `60`
  - `INSERT (c)`: **40** eventos (`+ R$ 261,072.70` adicionados)
  - `UPDATE (u)`: **12** eventos (`R$ +6,019.00` variação líquida)
  - `DELETE (d)`: **8** eventos (`- R$ 69,902.00` removidos)
  - `SKIPPED (Idempotência/Out-of-Order)`: **0** eventos barrados
- **Latência Média de Replicação (Source -> Silver):** `318.08 ms` (Máx: `602 ms`)

---

## 3. Estado Atual da Camada Silver por Status Operacional

| Status do Pedido | Quantidade Ativa | GMV Acumulado (R$) |
| :--- | :---: | :---: |
| `CREATED` | 24 | R$ 143,323.00 |
| `PAID` | 4 | R$ 33,596.70 |
| `CANCELLED` | 2 | R$ 17,341.50 |
| `SHIPPED` | 1 | R$ 1,948.50 |
| `REFUNDED` | 1 | R$ 980.00 |

## 4. Distribuição Geográfica na Camada Silver (Regiões)

| Região | Pedidos Ativos | GMV Acumulado (R$) |
| :--- | :---: | :---: |
| `Sul` | 8 | R$ 77,215.20 |
| `Sudeste` | 10 | R$ 54,835.60 |
| `Nordeste` | 6 | R$ 44,904.90 |
| `Centro-Oeste` | 7 | R$ 18,285.50 |
| `Norte` | 1 | R$ 1,948.50 |

---

## 5. Governança e Alertas de Auditoria (Deleções de Alto Valor >= R$ 3.000,00)

| LSN | Transaction ID | Order ID | Valor Removido (R$) | Horário Aplicação (UTC) |
| :---: | :---: | :---: | :---: | :---: |
| `36` | `d1178ae15a52dd8a` | `ORD-375AF3B6` | R$ 37,499.50 | `2026-11-02T02:04:28.322Z` |
| `22` | `145b269d8b085e7d` | `ORD-5B4BDB07` | R$ 10,995.00 | `2026-11-02T02:04:28.309Z` |
| `53` | `51b23e9fcfa538c3` | `ORD-D6D4DA69` | R$ 7,560.00 | `2026-11-02T02:04:28.949Z` |
| `13` | `6429d5cceed8fdc3` | `ORD-7908D0A2` | R$ 4,299.00 | `2026-11-02T02:04:27.786Z` |
| `30` | `219cc1d7989a8bea` | `ORD-28D33946` | R$ 3,780.00 | `2026-11-02T02:04:28.309Z` |

---

## 6. Amostra das Últimas 10 Mutações Aplicadas (Linhagem CDC)

| LSN | Operação | Order ID | Impacto (R$) | Lag (ms) | Campos Alterados (Diff) |
| :---: | :---: | :---: | :---: | :---: | :--- |
| `60` | **INSERT** | `ORD-D74993EE` | R$ +5,600.00 | `66` | `-` |
| `59` | **UPDATE** | `ORD-01C68433` | R$ +0.00 | `99` | `{"status": {"before": "PAID", "after": "SHIPPED"}}` |
| `58` | **DELETE** | `ORD-4BA88C7A` | R$ -2,700.00 | `140` | `-` |
| `57` | **INSERT** | `ORD-2606C5CE` | R$ +649.50 | `161` | `-` |
| `56` | **INSERT** | `ORD-5222DD80` | R$ +22,499.70 | `182` | `-` |
| `55` | **INSERT** | `ORD-4BA88C7A` | R$ +2,700.00 | `206` | `-` |
| `54` | **INSERT** | `ORD-8D265779` | R$ +17,196.00 | `228` | `-` |
| `53` | **DELETE** | `ORD-D6D4DA69` | R$ -7,560.00 | `262` | `-` |
| `52` | **INSERT** | `ORD-B1EEF0F4` | R$ +2,700.00 | `300` | `-` |
| `51` | **INSERT** | `ORD-65BF2323` | R$ +7,499.90 | `352` | `-` |
