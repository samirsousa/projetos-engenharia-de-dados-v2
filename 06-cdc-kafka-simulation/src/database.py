"""Camada de acesso a dados, DDL e triggers de captura CDC para OLTP e Silver."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


OLTP_DDL_SCRIPT = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- 1. Tabela Transacional de Domínio (OLTP - Pedidos / Transações Comerciais)
CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    customer_id     TEXT NOT NULL,
    customer_name   TEXT NOT NULL,
    product_sku     TEXT NOT NULL,
    category        TEXT NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      REAL NOT NULL CHECK (unit_price >= 0),
    total_amount    REAL NOT NULL CHECK (total_amount >= 0),
    status          TEXT NOT NULL CHECK (status IN ('CREATED', 'PAID', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'REFUNDED')),
    payment_method  TEXT NOT NULL,
    region          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 2. Tabela Interna de Log de Alterações (Simulação de WAL / Binlog de Banco de Dados)
-- Populada de forma 100% atômica dentro da mesma transação ACID via Database Triggers
CREATE TABLE IF NOT EXISTS _cdc_wal_log (
    lsn             INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_id           TEXT NOT NULL,
    op              TEXT NOT NULL CHECK (op IN ('c', 'u', 'd', 'r')),
    op_type         TEXT NOT NULL CHECK (op_type IN ('INSERT', 'UPDATE', 'DELETE', 'SNAPSHOT')),
    schema_name     TEXT NOT NULL DEFAULT 'main',
    table_name      TEXT NOT NULL,
    record_pk       TEXT NOT NULL,
    before_json     TEXT,
    after_json      TEXT,
    ts_ms           INTEGER NOT NULL,
    event_time_utc  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cdc_wal_log_lsn ON _cdc_wal_log(lsn);
CREATE INDEX IF NOT EXISTS idx_cdc_wal_log_ts_ms ON _cdc_wal_log(ts_ms);

-- 3. Triggers de Captura Automática (AFTER INSERT / UPDATE / DELETE)
CREATE TRIGGER IF NOT EXISTS trg_orders_cdc_insert
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO _cdc_wal_log (
        tx_id, op, op_type, schema_name, table_name, record_pk,
        before_json, after_json, ts_ms, event_time_utc
    )
    VALUES (
        lower(hex(randomblob(8))),
        'c',
        'INSERT',
        'main',
        'orders',
        NEW.order_id,
        NULL,
        json_object(
            'order_id', NEW.order_id,
            'customer_id', NEW.customer_id,
            'customer_name', NEW.customer_name,
            'product_sku', NEW.product_sku,
            'category', NEW.category,
            'quantity', NEW.quantity,
            'unit_price', ROUND(NEW.unit_price, 2),
            'total_amount', ROUND(NEW.total_amount, 2),
            'status', NEW.status,
            'payment_method', NEW.payment_method,
            'region', NEW.region,
            'created_at', NEW.created_at,
            'updated_at', NEW.updated_at
        ),
        CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER),
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_orders_cdc_update
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    INSERT INTO _cdc_wal_log (
        tx_id, op, op_type, schema_name, table_name, record_pk,
        before_json, after_json, ts_ms, event_time_utc
    )
    VALUES (
        lower(hex(randomblob(8))),
        'u',
        'UPDATE',
        'main',
        'orders',
        NEW.order_id,
        json_object(
            'order_id', OLD.order_id,
            'customer_id', OLD.customer_id,
            'customer_name', OLD.customer_name,
            'product_sku', OLD.product_sku,
            'category', OLD.category,
            'quantity', OLD.quantity,
            'unit_price', ROUND(OLD.unit_price, 2),
            'total_amount', ROUND(OLD.total_amount, 2),
            'status', OLD.status,
            'payment_method', OLD.payment_method,
            'region', OLD.region,
            'created_at', OLD.created_at,
            'updated_at', OLD.updated_at
        ),
        json_object(
            'order_id', NEW.order_id,
            'customer_id', NEW.customer_id,
            'customer_name', NEW.customer_name,
            'product_sku', NEW.product_sku,
            'category', NEW.category,
            'quantity', NEW.quantity,
            'unit_price', ROUND(NEW.unit_price, 2),
            'total_amount', ROUND(NEW.total_amount, 2),
            'status', NEW.status,
            'payment_method', NEW.payment_method,
            'region', NEW.region,
            'created_at', NEW.created_at,
            'updated_at', NEW.updated_at
        ),
        CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER),
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_orders_cdc_delete
AFTER DELETE ON orders
FOR EACH ROW
BEGIN
    INSERT INTO _cdc_wal_log (
        tx_id, op, op_type, schema_name, table_name, record_pk,
        before_json, after_json, ts_ms, event_time_utc
    )
    VALUES (
        lower(hex(randomblob(8))),
        'd',
        'DELETE',
        'main',
        'orders',
        OLD.order_id,
        json_object(
            'order_id', OLD.order_id,
            'customer_id', OLD.customer_id,
            'customer_name', OLD.customer_name,
            'product_sku', OLD.product_sku,
            'category', OLD.category,
            'quantity', OLD.quantity,
            'unit_price', ROUND(OLD.unit_price, 2),
            'total_amount', ROUND(OLD.total_amount, 2),
            'status', OLD.status,
            'payment_method', OLD.payment_method,
            'region', OLD.region,
            'created_at', OLD.created_at,
            'updated_at', OLD.updated_at
        ),
        NULL,
        CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER),
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    );
END;
"""


SILVER_DDL_SCRIPT = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- 1. Tabela Espelho Camada Silver (Estado Consolidado + Metadados de Linhagem CDC)
CREATE TABLE IF NOT EXISTS silver_orders (
    order_id            TEXT PRIMARY KEY,
    customer_id         TEXT NOT NULL,
    customer_name       TEXT NOT NULL,
    product_sku         TEXT NOT NULL,
    category            TEXT NOT NULL,
    quantity            INTEGER NOT NULL,
    unit_price          REAL NOT NULL,
    total_amount        REAL NOT NULL,
    status              TEXT NOT NULL,
    payment_method      TEXT NOT NULL,
    region              TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    -- Colunas Técnicas de Governança & CDC na Camada Silver
    _cdc_last_lsn       INTEGER NOT NULL,
    _cdc_last_op        TEXT NOT NULL,
    _cdc_tx_id          TEXT NOT NULL,
    _cdc_source_ts_ms   INTEGER NOT NULL,
    _cdc_ingested_at    TEXT NOT NULL,
    _is_deleted         INTEGER NOT NULL DEFAULT 0 CHECK (_is_deleted IN (0, 1)),
    _deleted_at         TEXT,
    _record_version     INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_silver_orders_active ON silver_orders(_is_deleted);
CREATE INDEX IF NOT EXISTS idx_silver_orders_status ON silver_orders(status);
CREATE INDEX IF NOT EXISTS idx_silver_orders_region ON silver_orders(region);

-- 2. View de Registros Ativos (Espelho Exato da Tabela OLTP em Produção)
CREATE VIEW IF NOT EXISTS vw_silver_orders_active AS
SELECT
    order_id,
    customer_id,
    customer_name,
    product_sku,
    category,
    quantity,
    unit_price,
    total_amount,
    status,
    payment_method,
    region,
    created_at,
    updated_at,
    _cdc_last_lsn,
    _record_version
FROM silver_orders
WHERE _is_deleted = 0;

-- 3. Tabela de Trilha de Auditoria Histórica (Append-Only Ledger de Eventos Aplicados)
CREATE TABLE IF NOT EXISTS silver_cdc_audit_log (
    audit_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_file          TEXT NOT NULL,
    lsn                 INTEGER NOT NULL UNIQUE,
    tx_id               TEXT NOT NULL,
    op                  TEXT NOT NULL,
    op_type             TEXT NOT NULL,
    table_name          TEXT NOT NULL,
    record_pk           TEXT NOT NULL,
    before_state_json   TEXT,
    after_state_json    TEXT,
    changed_fields_json TEXT,
    amount_delta        REAL NOT NULL DEFAULT 0.0,
    source_ts_ms        INTEGER NOT NULL,
    source_event_date   TEXT NOT NULL,
    applied_at_utc      TEXT NOT NULL,
    replication_lag_ms  INTEGER NOT NULL,
    apply_status        TEXT NOT NULL CHECK (apply_status IN ('APPLIED', 'SKIPPED_STALE_LSN', 'DUPLICATE_LSN'))
);

CREATE INDEX IF NOT EXISTS idx_silver_audit_date ON silver_cdc_audit_log(source_event_date);
CREATE INDEX IF NOT EXISTS idx_silver_audit_op ON silver_cdc_audit_log(op_type);
CREATE INDEX IF NOT EXISTS idx_silver_audit_pk ON silver_cdc_audit_log(record_pk);

-- 4. Controle de Arquivos de Lote Processados (Idempotência de Micro-Batch)
CREATE TABLE IF NOT EXISTS silver_processed_batches (
    batch_filename      TEXT PRIMARY KEY,
    file_sha256         TEXT NOT NULL,
    events_total        INTEGER NOT NULL,
    events_applied      INTEGER NOT NULL,
    events_skipped      INTEGER NOT NULL,
    min_lsn             INTEGER,
    max_lsn             INTEGER,
    processed_at_utc    TEXT NOT NULL
);
"""


@contextmanager
def get_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Gerenciador de contexto transacional seguro para conexões SQLite."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_oltp_database(db_path: Path) -> None:
    """Inicializa o banco de dados relacional de origem (OLTP) e as triggers CDC."""
    with get_connection(db_path) as conn:
        conn.executescript(OLTP_DDL_SCRIPT)


def init_silver_database(db_path: Path) -> None:
    """Inicializa o banco de dados analítico destino (Camada Silver)."""
    with get_connection(db_path) as conn:
        conn.executescript(SILVER_DDL_SCRIPT)
