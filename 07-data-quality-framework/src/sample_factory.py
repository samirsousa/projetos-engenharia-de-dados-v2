"""
Fábrica de Datasets e Contratos de Exemplo (CSV, Apache Parquet e SQLite).

Gera dados sintéticos realistas — incluindo cenários com anomalias intencionais
(violação de nulidade, IDs duplicados, extrapolação de limites e corrupção de tipo)
e cenários 100% íntegros — para demonstrar e testar o Data Quality Framework.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.config import DQConfig
from src.contracts import ColumnContract, DataContract, ExpectedDataType, RuleSeverity


def build_csv_transactions_sample(config: DQConfig) -> Tuple[Path, DataContract]:
    """Cria arquivo CSV de transações financeiras e seu respectivo Data Contract."""
    csv_path = config.samples_dir / "financial_transactions.csv"
    contract_path = config.contracts_dir / "contract_financial_transactions.json"

    fieldnames = [
        "transaction_id",
        "customer_id",
        "amount",
        "currency",
        "risk_score",
        "transaction_date",
        "customer_email",
    ]

    rows = [
        # Registros saudáveis
        {
            "transaction_id": "TXN-1001",
            "customer_id": "CUST-501",
            "amount": "1450.75",
            "currency": "BRL",
            "risk_score": "12",
            "transaction_date": "2026-11-01",
            "customer_email": "ana.silva@empresa.com.br",
        },
        {
            "transaction_id": "TXN-1002",
            "customer_id": "CUST-502",
            "amount": "320.00",
            "currency": "BRL",
            "risk_score": "5",
            "transaction_date": "2026-11-01",
            "customer_email": "carlos.mendes@fintech.io",
        },
        {
            "transaction_id": "TXN-1003",
            "customer_id": "CUST-503",
            "amount": "8900.50",
            "currency": "USD",
            "risk_score": "44",
            "transaction_date": "2026-11-01",
            "customer_email": "fernanda.costa@global.org",
        },
        # ANOMALIA 1: Violação de Unicidade (ID TXN-1002 duplicado)
        {
            "transaction_id": "TXN-1002",
            "customer_id": "CUST-504",
            "amount": "210.00",
            "currency": "BRL",
            "risk_score": "18",
            "transaction_date": "2026-11-01",
            "customer_email": "duplicado@empresa.com.br",
        },
        # ANOMALIA 2: Violação de Nulidade (customer_id nulo / vazio)
        {
            "transaction_id": "TXN-1005",
            "customer_id": "",
            "amount": "540.00",
            "currency": "BRL",
            "risk_score": "22",
            "transaction_date": "2026-11-01",
            "customer_email": "sem.cliente@empresa.com.br",
        },
        # ANOMALIA 3: Violação de Limite Inferior e Superior (amount negativo e risk_score > 100)
        {
            "transaction_id": "TXN-1006",
            "customer_id": "CUST-506",
            "amount": "-450.00",
            "currency": "BRL",
            "risk_score": "145",
            "transaction_date": "2026-11-01",
            "customer_email": "limite.invalido@empresa.com.br",
        },
        # ANOMALIA 4: Violação de Tipo de Dado (amount texto não numérico e data inexistente)
        {
            "transaction_id": "TXN-1007",
            "customer_id": "CUST-507",
            "amount": "ERRO_PARSE_VALOR",
            "currency": "EUR",
            "risk_score": "30",
            "transaction_date": "2026-15-99",
            "customer_email": "tipo.corrompido@empresa.com.br",
        },
        # ANOMALIA 5: Violação de Domínio e Formato de E-mail (moeda CRYPTO e email inválido)
        {
            "transaction_id": "TXN-1008",
            "customer_id": "CUST-508",
            "amount": "1200.00",
            "currency": "DOGE",
            "risk_score": "50",
            "transaction_date": "2026-11-01",
            "customer_email": "email_sem_arroba_e_dominio",
        },
        # Mais registros saudáveis
        {
            "transaction_id": "TXN-1009",
            "customer_id": "CUST-509",
            "amount": "75.90",
            "currency": "BRL",
            "risk_score": "3",
            "transaction_date": "2026-11-01",
            "customer_email": "juliana.rocha@varejo.com.br",
        },
        {
            "transaction_id": "TXN-1010",
            "customer_id": "CUST-510",
            "amount": "4100.00",
            "currency": "EUR",
            "risk_score": "29",
            "transaction_date": "2026-11-01",
            "customer_email": "rafael.lima@banco.com",
        },
    ]

    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    contract = DataContract(
        contract_id="DC-FIN-CSV-001",
        dataset_name="Financial_Transactions_CSV",
        source_format="CSV",
        owner_team="Core-Payments-Engineering",
        primary_key_column="transaction_id",
        columns=[
            ColumnContract(
                name="transaction_id",
                expected_type=ExpectedDataType.STRING,
                nullable=False,
                unique=True,
                is_primary_key=True,
                regex_pattern=r"^TXN-\d{4,}$",
                severity=RuleSeverity.CRITICAL,
                description="Identificador único global da transação financeira.",
            ),
            ColumnContract(
                name="customer_id",
                expected_type=ExpectedDataType.STRING,
                nullable=False,
                severity=RuleSeverity.CRITICAL,
                description="Chave estrangeira obrigatória do cliente.",
            ),
            ColumnContract(
                name="amount",
                expected_type=ExpectedDataType.FLOAT,
                nullable=False,
                min_value=0.01,
                max_value=100000.00,
                severity=RuleSeverity.CRITICAL,
                description="Valor monetário da transação (estritamente positivo).",
            ),
            ColumnContract(
                name="currency",
                expected_type=ExpectedDataType.STRING,
                nullable=False,
                allowed_values=["BRL", "USD", "EUR"],
                severity=RuleSeverity.ERROR,
                description="Código ISO-4217 da moeda fiduciária.",
            ),
            ColumnContract(
                name="risk_score",
                expected_type=ExpectedDataType.INT,
                nullable=False,
                min_value=0,
                max_value=100,
                severity=RuleSeverity.ERROR,
                description="Score de risco antifraude entre 0 e 100.",
            ),
            ColumnContract(
                name="transaction_date",
                expected_type=ExpectedDataType.DATE,
                nullable=False,
                severity=RuleSeverity.CRITICAL,
                description="Data contábil no formato ISO YYYY-MM-DD.",
            ),
            ColumnContract(
                name="customer_email",
                expected_type=ExpectedDataType.EMAIL,
                nullable=False,
                severity=RuleSeverity.WARNING,
                description="E-mail de notificação de comprovante.",
            ),
        ],
    )
    contract.save_json(contract_path)
    return csv_path, contract


def build_parquet_telemetry_sample(config: DQConfig) -> Tuple[Path, DataContract]:
    """Cria arquivo Apache Parquet (.parquet) de telemetria IoT e seu Data Contract."""
    parquet_path = config.samples_dir / "iot_sensor_telemetry.parquet"
    contract_path = config.contracts_dir / "contract_iot_sensor_telemetry.json"

    records: List[Dict[str, Any]] = [
        {
            "reading_id": "SENS-9001",
            "device_id": "DEV-TURBINE-01",
            "temperature_c": "68.4",
            "humidity_pct": "45.2",
            "vibration_hz": "120",
            "status_code": "OK",
        },
        {
            "reading_id": "SENS-9002",
            "device_id": "DEV-TURBINE-02",
            "temperature_c": "72.1",
            "humidity_pct": "48.0",
            "vibration_hz": "115",
            "status_code": "OK",
        },
        # ANOMALIA 1: reading_id duplicado
        {
            "reading_id": "SENS-9002",
            "device_id": "DEV-TURBINE-03",
            "temperature_c": "74.0",
            "humidity_pct": "50.1",
            "vibration_hz": "118",
            "status_code": "WARN",
        },
        # ANOMALIA 2: device_id nulo
        {
            "reading_id": "SENS-9004",
            "device_id": None,
            "temperature_c": "65.0",
            "humidity_pct": "42.0",
            "vibration_hz": "110",
            "status_code": "OK",
        },
        # ANOMALIA 3: Range violation (temperatura 295.5°C > 125°C e umidade 135.0% > 100%)
        {
            "reading_id": "SENS-9005",
            "device_id": "DEV-TURBINE-01",
            "temperature_c": "295.5",
            "humidity_pct": "135.0",
            "vibration_hz": "140",
            "status_code": "CRITICAL",
        },
        # ANOMALIA 4: Tipo de dado corrompido (vibration_hz contém string alfanumérica)
        {
            "reading_id": "SENS-9006",
            "device_id": "DEV-TURBINE-04",
            "temperature_c": "70.2",
            "humidity_pct": "44.0",
            "vibration_hz": "SENSOR_OFFLINE_ERR",
            "status_code": "FAULT",
        },
        {
            "reading_id": "SENS-9007",
            "device_id": "DEV-TURBINE-02",
            "temperature_c": "69.8",
            "humidity_pct": "46.5",
            "vibration_hz": "112",
            "status_code": "OK",
        },
        {
            "reading_id": "SENS-9008",
            "device_id": "DEV-TURBINE-03",
            "temperature_c": "71.0",
            "humidity_pct": "47.0",
            "vibration_hz": "119",
            "status_code": "OK",
        },
    ]

    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore

        table = pa.Table.from_pylist(records)
        pq.write_table(table, parquet_path)
    except Exception:
        with open(parquet_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "columns": list(records[0].keys()),
                    "rows": records,
                },
                fh,
                indent=2,
            )

    contract = DataContract(
        contract_id="DC-IOT-PARQUET-002",
        dataset_name="IoT_Sensor_Telemetry_Parquet",
        source_format="PARQUET",
        owner_team="Industrial-IoT-Platform",
        primary_key_column="reading_id",
        columns=[
            ColumnContract(
                name="reading_id",
                expected_type=ExpectedDataType.STRING,
                nullable=False,
                unique=True,
                is_primary_key=True,
                severity=RuleSeverity.CRITICAL,
                description="ID único de pacote de telemetria.",
            ),
            ColumnContract(
                name="device_id",
                expected_type=ExpectedDataType.STRING,
                nullable=False,
                severity=RuleSeverity.CRITICAL,
                description="Identificador físico da turbina/sensor.",
            ),
            ColumnContract(
                name="temperature_c",
                expected_type=ExpectedDataType.FLOAT,
                nullable=False,
                min_value=-40.0,
                max_value=125.0,
                severity=RuleSeverity.CRITICAL,
                description="Temperatura operacional em graus Celsius (-40 a 125).",
            ),
            ColumnContract(
                name="humidity_pct",
                expected_type=ExpectedDataType.FLOAT,
                nullable=False,
                min_value=0.0,
                max_value=100.0,
                severity=RuleSeverity.ERROR,
                description="Umidade relativa do ar (0% a 100%).",
            ),
            ColumnContract(
                name="vibration_hz",
                expected_type=ExpectedDataType.INT,
                nullable=False,
                min_value=0,
                max_value=500,
                severity=RuleSeverity.CRITICAL,
                description="Frequência de vibração mecânica em Hz (inteiro).",
            ),
            ColumnContract(
                name="status_code",
                expected_type=ExpectedDataType.STRING,
                nullable=False,
                allowed_values=["OK", "WARN", "CRITICAL", "FAULT"],
                severity=RuleSeverity.WARNING,
                description="Código de estado operacional do sensor.",
            ),
        ],
    )
    contract.save_json(contract_path)
    return parquet_path, contract


def build_sqlite_customers_samples(
    config: DQConfig,
) -> Tuple[Path, DataContract, DataContract]:
    """
    Cria banco SQLite contendo:
    1. `customers_silver`: Tabela com anomalias de nulidade, unicidade, range e tipo (tipagem dinâmica SQLite).
    2. `customers_gold_clean`: Tabela 100% aderente ao Data Contract para validação de estado saudável.
    """
    db_path = config.samples_dir / "crm_warehouse.db"
    contract_silver_path = config.contracts_dir / "contract_sqlite_customers_silver.json"
    contract_gold_path = config.contracts_dir / "contract_sqlite_customers_gold.json"

    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        # Nota Técnica: O SQLite utiliza tipagem dinâmica (Type Affinity) e permite chaves
        # nulas ou duplicadas caso a tabela de staging/silver não possua constraints rígidas.
        conn.executescript(
            """
            CREATE TABLE customers_silver (
                customer_id     TEXT,
                full_name       TEXT,
                age             ANY,
                credit_limit    ANY,
                tier            TEXT,
                signup_date     TEXT
            );

            CREATE TABLE customers_gold_clean (
                customer_id     TEXT PRIMARY KEY,
                full_name       TEXT NOT NULL,
                age             INTEGER NOT NULL,
                credit_limit    REAL NOT NULL,
                tier            TEXT NOT NULL,
                signup_date     TEXT NOT NULL
            );
            """
        )

        silver_rows = [
            ("CUST-001", "Mariana Alves", 29, 15000.00, "GOLD", "2025-03-14"),
            ("CUST-002", "Pedro Henrique", 41, 32000.00, "PLATINUM", "2024-11-20"),
            # ANOMALIA 1: ID duplicado (CUST-002)
            ("CUST-002", "Pedro Clone Duplicado", 41, 32000.00, "PLATINUM", "2024-11-20"),
            # ANOMALIA 2: Coluna-chave full_name nula
            ("CUST-004", None, 35, 8500.00, "SILVER", "2026-01-10"),
            # ANOMALIA 3: Range violation (idade negativa -5 e credit_limit acima de 500.000)
            ("CUST-005", "Roberto Dias", -5, 950000.00, "BLACK_INVALID_TIER", "2026-02-18"),
            # ANOMALIA 4: Tipo de dado inválido (idade escrita por extenso 'TRINTA_E_DOIS')
            ("CUST-006", "Carla Souza", "TRINTA_E_DOIS", 12000.00, "SILVER", "2026-04-05"),
            ("CUST-007", "Lucas Oliveira", 52, 45000.00, "PLATINUM", "2023-08-01"),
        ]
        conn.executemany(
            "INSERT INTO customers_silver VALUES (?, ?, ?, ?, ?, ?)",
            silver_rows,
        )

        gold_rows = [
            ("CUST-001", "Mariana Alves", 29, 15000.00, "GOLD", "2025-03-14"),
            ("CUST-002", "Pedro Henrique", 41, 32000.00, "PLATINUM", "2024-11-20"),
            ("CUST-003", "Beatriz Santos", 34, 18500.00, "GOLD", "2025-07-22"),
            ("CUST-004", "Thiago Ferreira", 27, 9200.00, "SILVER", "2026-01-10"),
            ("CUST-005", "Lucas Oliveira", 52, 45000.00, "PLATINUM", "2023-08-01"),
        ]
        conn.executemany(
            "INSERT INTO customers_gold_clean VALUES (?, ?, ?, ?, ?, ?)",
            gold_rows,
        )
        conn.commit()
    finally:
        conn.close()

    common_columns = [
        ColumnContract(
            name="customer_id",
            expected_type=ExpectedDataType.STRING,
            nullable=False,
            unique=True,
            is_primary_key=True,
            regex_pattern=r"^CUST-\d{3,}$",
            severity=RuleSeverity.CRITICAL,
            description="Identificador único do cliente no CRM.",
        ),
        ColumnContract(
            name="full_name",
            expected_type=ExpectedDataType.STRING,
            nullable=False,
            severity=RuleSeverity.CRITICAL,
            description="Nome completo obrigatório para faturamento.",
        ),
        ColumnContract(
            name="age",
            expected_type=ExpectedDataType.INT,
            nullable=False,
            min_value=18,
            max_value=120,
            severity=RuleSeverity.ERROR,
            description="Idade civil válida para titularidade de crédito (18 a 120 anos).",
        ),
        ColumnContract(
            name="credit_limit",
            expected_type=ExpectedDataType.FLOAT,
            nullable=False,
            min_value=0.0,
            max_value=500000.0,
            severity=RuleSeverity.CRITICAL,
            description="Limite de crédito aprovado em reais (0 a 500.000).",
        ),
        ColumnContract(
            name="tier",
            expected_type=ExpectedDataType.STRING,
            nullable=False,
            allowed_values=["BRONZE", "SILVER", "GOLD", "PLATINUM"],
            severity=RuleSeverity.ERROR,
            description="Segmentação comercial do cliente.",
        ),
        ColumnContract(
            name="signup_date",
            expected_type=ExpectedDataType.DATE,
            nullable=False,
            severity=RuleSeverity.WARNING,
            description="Data de cadastro no formato ISO YYYY-MM-DD.",
        ),
    ]

    contract_silver = DataContract(
        contract_id="DC-CRM-SQLITE-003",
        dataset_name="CRM_Customers_Silver_SQLite",
        source_format="SQLITE",
        owner_team="Customer-Data-Platform",
        primary_key_column="customer_id",
        columns=common_columns,
    )
    contract_silver.save_json(contract_silver_path)

    contract_gold = DataContract(
        contract_id="DC-CRM-SQLITE-004",
        dataset_name="CRM_Customers_Gold_Clean_SQLite",
        source_format="SQLITE",
        owner_team="Customer-Data-Platform",
        primary_key_column="customer_id",
        columns=common_columns,
    )
    contract_gold.save_json(contract_gold_path)

    return db_path, contract_silver, contract_gold
