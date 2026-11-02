# Relatório Executivo de Data Quality & Observability

Consolidação da bateria de testes de **Data Contracts** executada sobre arquivos **CSV**, **Apache Parquet** e tabelas **SQLite**.

## 1. Visão Geral de Saúde dos Datasets (SLIs de Qualidade)

| Contrato ID | Dataset | Formato | Linhas Totais | Saudáveis | Corrompidas | DQ Score (%) | Anomalias | Status do Contrato |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `DC-FIN-CSV-001` | `Financial_Transactions_CSV` | **CSV** | 10 | 5 | 5 | `50.00%` | `8` | **VIOLADO (FAIL)** |
| `DC-IOT-PARQUET-002` | `IoT_Sensor_Telemetry_Parquet` | **PARQUET** | 8 | 4 | 4 | `50.00%` | `5` | **VIOLADO (FAIL)** |
| `DC-CRM-SQLITE-003` | `CRM_Customers_Silver_SQLite` | **SQLITE** | 7 | 3 | 4 | `42.86%` | `6` | **VIOLADO (FAIL)** |
| `DC-CRM-SQLITE-004` | `CRM_Customers_Gold_Clean_SQLite` | **SQLITE** | 5 | 5 | 0 | `100.00%` | `0` | **APROVADO (PASS)** |

---

## 2. Detalhamento por Fonte e Violações de Contrato

### 2.1. `Financial_Transactions_CSV` (CSV — `financial_transactions.csv`)

- **Run ID:** `DQ-RUN-492A97BE` | **Equipe Responsável:** `Core-Payments-Engineering` | **Tempo de Execução:** `0.57 ms`
- **Data Quality Score:** `50.00%` (5/10 registros conformes)

#### Resumo de Regras Avaliadas

| Categoria | Regra | Coluna | Avaliados | Falhas | Taxa de Sucesso | Status |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| `SCHEMA_CHECK` | `required_columns_exist` | `*` | 7 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `transaction_id` | 10 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_string` | `transaction_id` | 10 | 0 | `100.00%` | **OK** |
| `UNIQUENESS` | `unique_id_check` | `transaction_id` | 10 | 1 | `90.00%` | **FALHA** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `transaction_id` | 10 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `customer_id` | 10 | 1 | `90.00%` | **FALHA** |
| `DATA_TYPE` | `type_check_string` | `customer_id` | 9 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `amount` | 10 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_float` | `amount` | 10 | 1 | `90.00%` | **FALHA** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `amount` | 9 | 1 | `88.89%` | **FALHA** |
| `NULLABILITY` | `not_null_check` | `currency` | 10 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_string` | `currency` | 10 | 0 | `100.00%` | **OK** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `currency` | 10 | 1 | `90.00%` | **FALHA** |
| `NULLABILITY` | `not_null_check` | `risk_score` | 10 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_int` | `risk_score` | 10 | 0 | `100.00%` | **OK** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `risk_score` | 10 | 1 | `90.00%` | **FALHA** |
| `NULLABILITY` | `not_null_check` | `transaction_date` | 10 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_date` | `transaction_date` | 10 | 1 | `90.00%` | **FALHA** |
| `NULLABILITY` | `not_null_check` | `customer_email` | 10 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_email` | `customer_email` | 10 | 1 | `90.00%` | **FALHA** |

#### Anomalias Capturadas (Data Contract Violations)

| ID | Categoria | Severidade | Linha | PK | Coluna | Valor Observado | Restrição Esperada | Diagnóstico |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `VIOL-0001` | `UNIQUENESS` | **CRITICAL** | `4` | `TXN-1002` | `transaction_id` | `'TXN-1002'` | `UNIQUE` | ID duplicado 'TXN-1002' na coluna 'transaction_id' (linha 4 colide com a linha 2). |
| `VIOL-0002` | `NULLABILITY` | **CRITICAL** | `5` | `TXN-1005` | `customer_id` | `''` | `NOT NULL` | Valor nulo ou vazio detectado na coluna-chave 'customer_id' (linha 5, PK=TXN-1005). |
| `VIOL-0003` | `RANGE_CHECK` | **CRITICAL** | `6` | `TXN-1006` | `amount` | `-450.0` | `>= 0.01` | Valor -450.0 abaixo do limite mínimo permitido (0.01) na coluna 'amount' (linha 6, PK=TXN-1006). |
| `VIOL-0004` | `DATA_TYPE` | **CRITICAL** | `7` | `TXN-1007` | `amount` | `'ERRO_PARSE_VALOR'` | `TYPE == FLOAT` | Violação de tipo na coluna 'amount' (linha 7, PK=TXN-1007): String 'ERRO_PARSE_VALOR' não pode ser convertida para FLOAT. |
| `VIOL-0005` | `RANGE_CHECK` | **ERROR** | `8` | `TXN-1008` | `currency` | `'DOGE'` | `IN ['BRL', 'USD', 'EUR']` | Valor 'DOGE' fora do domínio permitido ['BRL', 'USD', 'EUR'] na coluna 'currency' (linha 8, PK=TXN-1008). |
| `VIOL-0006` | `RANGE_CHECK` | **ERROR** | `6` | `TXN-1006` | `risk_score` | `145` | `<= 100` | Valor 145 acima do limite máximo permitido (100) na coluna 'risk_score' (linha 6, PK=TXN-1006). |
| `VIOL-0007` | `DATA_TYPE` | **CRITICAL** | `7` | `TXN-1007` | `transaction_date` | `'2026-15-99'` | `TYPE == DATE` | Violação de tipo na coluna 'transaction_date' (linha 7, PK=TXN-1007): Data '2026-15-99' fora do formato ISO-8601 (YYYY-MM-DD). |
| `VIOL-0008` | `DATA_TYPE` | **WARNING** | `8` | `TXN-1008` | `customer_email` | `'email_sem_arroba_e_dominio'` | `TYPE == EMAIL` | Violação de tipo na coluna 'customer_email' (linha 8, PK=TXN-1008): Valor 'email_sem_arroba_e_dominio' não é um endereço de e-mail válido. |

### 2.2. `IoT_Sensor_Telemetry_Parquet` (PARQUET — `iot_sensor_telemetry.parquet`)

- **Run ID:** `DQ-RUN-F2BDE201` | **Equipe Responsável:** `Industrial-IoT-Platform` | **Tempo de Execução:** `0.29 ms`
- **Data Quality Score:** `50.00%` (4/8 registros conformes)

#### Resumo de Regras Avaliadas

| Categoria | Regra | Coluna | Avaliados | Falhas | Taxa de Sucesso | Status |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| `SCHEMA_CHECK` | `required_columns_exist` | `*` | 6 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `reading_id` | 8 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_string` | `reading_id` | 8 | 0 | `100.00%` | **OK** |
| `UNIQUENESS` | `unique_id_check` | `reading_id` | 8 | 1 | `87.50%` | **FALHA** |
| `NULLABILITY` | `not_null_check` | `device_id` | 8 | 1 | `87.50%` | **FALHA** |
| `DATA_TYPE` | `type_check_string` | `device_id` | 7 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `temperature_c` | 8 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_float` | `temperature_c` | 8 | 0 | `100.00%` | **OK** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `temperature_c` | 8 | 1 | `87.50%` | **FALHA** |
| `NULLABILITY` | `not_null_check` | `humidity_pct` | 8 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_float` | `humidity_pct` | 8 | 0 | `100.00%` | **OK** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `humidity_pct` | 8 | 1 | `87.50%` | **FALHA** |
| `NULLABILITY` | `not_null_check` | `vibration_hz` | 8 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_int` | `vibration_hz` | 8 | 1 | `87.50%` | **FALHA** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `vibration_hz` | 7 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `status_code` | 8 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_string` | `status_code` | 8 | 0 | `100.00%` | **OK** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `status_code` | 8 | 0 | `100.00%` | **OK** |

#### Anomalias Capturadas (Data Contract Violations)

| ID | Categoria | Severidade | Linha | PK | Coluna | Valor Observado | Restrição Esperada | Diagnóstico |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `VIOL-0001` | `UNIQUENESS` | **CRITICAL** | `3` | `SENS-9002` | `reading_id` | `'SENS-9002'` | `UNIQUE` | ID duplicado 'SENS-9002' na coluna 'reading_id' (linha 3 colide com a linha 2). |
| `VIOL-0002` | `NULLABILITY` | **CRITICAL** | `4` | `SENS-9004` | `device_id` | `None` | `NOT NULL` | Valor nulo ou vazio detectado na coluna-chave 'device_id' (linha 4, PK=SENS-9004). |
| `VIOL-0003` | `RANGE_CHECK` | **CRITICAL** | `5` | `SENS-9005` | `temperature_c` | `295.5` | `<= 125.0` | Valor 295.5 acima do limite máximo permitido (125.0) na coluna 'temperature_c' (linha 5, PK=SENS-9005). |
| `VIOL-0004` | `RANGE_CHECK` | **ERROR** | `5` | `SENS-9005` | `humidity_pct` | `135.0` | `<= 100.0` | Valor 135.0 acima do limite máximo permitido (100.0) na coluna 'humidity_pct' (linha 5, PK=SENS-9005). |
| `VIOL-0005` | `DATA_TYPE` | **CRITICAL** | `6` | `SENS-9006` | `vibration_hz` | `'SENSOR_OFFLINE_ERR'` | `TYPE == INT` | Violação de tipo na coluna 'vibration_hz' (linha 6, PK=SENS-9006): String 'SENSOR_OFFLINE_ERR' não representa um inteiro válido. |

### 2.3. `CRM_Customers_Silver_SQLite` (SQLITE — `crm_warehouse.db::customers_silver`)

- **Run ID:** `DQ-RUN-F1BC7F91` | **Equipe Responsável:** `Customer-Data-Platform` | **Tempo de Execução:** `0.28 ms`
- **Data Quality Score:** `42.86%` (3/7 registros conformes)

#### Resumo de Regras Avaliadas

| Categoria | Regra | Coluna | Avaliados | Falhas | Taxa de Sucesso | Status |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| `SCHEMA_CHECK` | `required_columns_exist` | `*` | 6 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `customer_id` | 7 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_string` | `customer_id` | 7 | 0 | `100.00%` | **OK** |
| `UNIQUENESS` | `unique_id_check` | `customer_id` | 7 | 1 | `85.71%` | **FALHA** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `customer_id` | 7 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `full_name` | 7 | 1 | `85.71%` | **FALHA** |
| `DATA_TYPE` | `type_check_string` | `full_name` | 6 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `age` | 7 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_int` | `age` | 7 | 1 | `85.71%` | **FALHA** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `age` | 6 | 1 | `83.33%` | **FALHA** |
| `NULLABILITY` | `not_null_check` | `credit_limit` | 7 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_float` | `credit_limit` | 7 | 0 | `100.00%` | **OK** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `credit_limit` | 7 | 1 | `85.71%` | **FALHA** |
| `NULLABILITY` | `not_null_check` | `tier` | 7 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_string` | `tier` | 7 | 0 | `100.00%` | **OK** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `tier` | 7 | 1 | `85.71%` | **FALHA** |
| `NULLABILITY` | `not_null_check` | `signup_date` | 7 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_date` | `signup_date` | 7 | 0 | `100.00%` | **OK** |

#### Anomalias Capturadas (Data Contract Violations)

| ID | Categoria | Severidade | Linha | PK | Coluna | Valor Observado | Restrição Esperada | Diagnóstico |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `VIOL-0001` | `UNIQUENESS` | **CRITICAL** | `3` | `CUST-002` | `customer_id` | `'CUST-002'` | `UNIQUE` | ID duplicado 'CUST-002' na coluna 'customer_id' (linha 3 colide com a linha 2). |
| `VIOL-0002` | `NULLABILITY` | **CRITICAL** | `4` | `CUST-004` | `full_name` | `None` | `NOT NULL` | Valor nulo ou vazio detectado na coluna-chave 'full_name' (linha 4, PK=CUST-004). |
| `VIOL-0003` | `RANGE_CHECK` | **ERROR** | `5` | `CUST-005` | `age` | `-5` | `>= 18` | Valor -5 abaixo do limite mínimo permitido (18) na coluna 'age' (linha 5, PK=CUST-005). |
| `VIOL-0004` | `DATA_TYPE` | **ERROR** | `6` | `CUST-006` | `age` | `'TRINTA_E_DOIS'` | `TYPE == INT` | Violação de tipo na coluna 'age' (linha 6, PK=CUST-006): String 'TRINTA_E_DOIS' não representa um inteiro válido. |
| `VIOL-0005` | `RANGE_CHECK` | **CRITICAL** | `5` | `CUST-005` | `credit_limit` | `950000.0` | `<= 500000.0` | Valor 950000.0 acima do limite máximo permitido (500000.0) na coluna 'credit_limit' (linha 5, PK=CUST-005). |
| `VIOL-0006` | `RANGE_CHECK` | **ERROR** | `5` | `CUST-005` | `tier` | `'BLACK_INVALID_TIER'` | `IN ['BRONZE', 'SILVER', 'GOLD', 'PLATINUM']` | Valor 'BLACK_INVALID_TIER' fora do domínio permitido ['BRONZE', 'SILVER', 'GOLD', 'PLATINUM'] na coluna 'tier' (linha 5, PK=CUST-005). |

### 2.4. `CRM_Customers_Gold_Clean_SQLite` (SQLITE — `crm_warehouse.db::customers_gold_clean`)

- **Run ID:** `DQ-RUN-A84C46F7` | **Equipe Responsável:** `Customer-Data-Platform` | **Tempo de Execução:** `0.16 ms`
- **Data Quality Score:** `100.00%` (5/5 registros conformes)

#### Resumo de Regras Avaliadas

| Categoria | Regra | Coluna | Avaliados | Falhas | Taxa de Sucesso | Status |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| `SCHEMA_CHECK` | `required_columns_exist` | `*` | 6 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `customer_id` | 5 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_string` | `customer_id` | 5 | 0 | `100.00%` | **OK** |
| `UNIQUENESS` | `unique_id_check` | `customer_id` | 5 | 0 | `100.00%` | **OK** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `customer_id` | 5 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `full_name` | 5 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_string` | `full_name` | 5 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `age` | 5 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_int` | `age` | 5 | 0 | `100.00%` | **OK** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `age` | 5 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `credit_limit` | 5 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_float` | `credit_limit` | 5 | 0 | `100.00%` | **OK** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `credit_limit` | 5 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `tier` | 5 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_string` | `tier` | 5 | 0 | `100.00%` | **OK** |
| `RANGE_CHECK` | `domain_and_range_bounds` | `tier` | 5 | 0 | `100.00%` | **OK** |
| `NULLABILITY` | `not_null_check` | `signup_date` | 5 | 0 | `100.00%` | **OK** |
| `DATA_TYPE` | `type_check_date` | `signup_date` | 5 | 0 | `100.00%` | **OK** |

> Nenhuma anomalia detectada. Dataset 100% em conformidade com o contrato.
