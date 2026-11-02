"""
Gerador da Base de Dados Transacional de E-Commerce (Camada Bronze / OLTP).

Cria um banco relacional SQLite (`ecommerce_oltp.db`) contendo perfis comportamentais
distintos de clientes (VIP Champions, Compradores Sazonais de Fim de Semana,
Caçadores de Desconto, Clientes em Risco de Churn e Novos Clientes) ao longo de 13 meses.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.config import FeatureStoreConfig, setup_logger

logger = setup_logger("OLTP-Ecommerce-Seeder")


OLTP_ECOMMERCE_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    customer_id         TEXT PRIMARY KEY,
    full_name           TEXT NOT NULL,
    state_uf            TEXT NOT NULL,
    acquisition_channel TEXT NOT NULL,
    signup_date         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id            TEXT PRIMARY KEY,
    customer_id         TEXT NOT NULL REFERENCES customers(customer_id),
    order_timestamp     TEXT NOT NULL,
    product_category    TEXT NOT NULL,
    items_count         INTEGER NOT NULL CHECK (items_count > 0),
    gross_amount        REAL NOT NULL CHECK (gross_amount > 0),
    discount_amount     REAL NOT NULL DEFAULT 0.0 CHECK (discount_amount >= 0),
    net_amount          REAL NOT NULL CHECK (net_amount > 0),
    payment_method      TEXT NOT NULL,
    order_status        TEXT NOT NULL CHECK (order_status IN ('COMPLETED', 'CANCELLED', 'REFUNDED'))
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_ts ON orders(customer_id, order_timestamp);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status);
"""

CATEGORIES = [
    ("Eletronicos", 850.0, 4200.0),
    ("Informatica", 320.0, 2800.0),
    ("Moda_Esportiva", 120.0, 580.0),
    ("Casa_Decoracao", 150.0, 1400.0),
    ("Livros_Educacao", 45.0, 290.0),
    ("Beleza_Saude", 65.0, 490.0),
    ("Games_Consoles", 250.0, 3500.0),
    ("Supermercado_Gourmet", 90.0, 620.0),
]

STATES_UF = ["SP", "RJ", "MG", "PR", "RS", "SC", "BA", "PE", "DF", "GO"]
CHANNELS = ["ORGANIC_SEARCH", "PAID_SOCIAL", "REFERRAL", "CRM_EMAIL", "INFLUENCER"]
PAYMENTS = ["PIX", "CREDIT_CARD", "BOLETO", "DIGITAL_WALLET"]


class EcommerceOLTPSeeder:
    """Popula o banco OLTP de e-commerce com histórico transacional rico para ML."""

    def __init__(self, config: Optional[FeatureStoreConfig] = None, seed: int = 42) -> None:
        self.config = config or FeatureStoreConfig()
        self.config.ensure_directories()
        self.rng = random.Random(seed)

    def seed_database(self, num_customers: int = 60) -> Dict[str, int]:
        """Gera clientes e transações históricas no banco SQLite OLTP."""
        db_path = self.config.oltp_db_path
        if db_path.exists():
            db_path.unlink()

        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(OLTP_ECOMMERCE_DDL)

            base_cutoff = datetime(2026, 10, 1, 23, 59, 59, tzinfo=timezone.utc)
            customers_rows: List[Tuple[str, str, str, str, str]] = []
            orders_rows: List[Tuple[str, str, str, str, int, float, float, float, str, str]] = []

            archetypes = [
                "CHAMPION_HIGH_FREQ",
                "LOYAL_STEADY",
                "WEEKEND_BARGAIN_HUNTER",
                "AT_RISK_DECELERATING",
                "HIBERNATING_CHURNED",
                "RECENT_PROMISING",
            ]

            order_seq = 10000

            for idx in range(1, num_customers + 1):
                customer_id = f"CUST-{idx:04d}"
                archetype = archetypes[(idx - 1) % len(archetypes)]
                state_uf = self.rng.choice(STATES_UF)
                channel = self.rng.choice(CHANNELS)

                if archetype == "RECENT_PROMISING":
                    days_since_signup = self.rng.randint(25, 75)
                else:
                    days_since_signup = self.rng.randint(180, 420)

                signup_dt = base_cutoff - timedelta(days=days_since_signup)
                customers_rows.append(
                    (
                        customer_id,
                        f"Cliente E-Commerce #{idx:04d} ({archetype.split('_')[0]})",
                        state_uf,
                        channel,
                        signup_dt.strftime("%Y-%m-%d"),
                    )
                )

                # Define padrão de compras pré-cutoff (até 2026-10-01) e pós-cutoff (outubro/2026)
                tx_timestamps: List[datetime] = []

                if archetype == "CHAMPION_HIGH_FREQ":
                    n_orders = self.rng.randint(14, 24)
                    for _ in range(n_orders):
                        offset_days = self.rng.randint(1, days_since_signup - 2)
                        hour = self.rng.choice([10, 11, 14, 15, 20, 21])
                        tx_timestamps.append(
                            base_cutoff - timedelta(days=offset_days, hours=23 - hour, minutes=self.rng.randint(0, 59))
                        )
                    # Compra também na janela futura de 30 dias (Não-Churn)
                    for _ in range(self.rng.randint(2, 5)):
                        tx_timestamps.append(
                            base_cutoff + timedelta(days=self.rng.randint(2, 28), hours=self.rng.randint(8, 22))
                        )

                elif archetype == "LOYAL_STEADY":
                    n_orders = self.rng.randint(8, 14)
                    for _ in range(n_orders):
                        offset_days = self.rng.randint(5, days_since_signup - 2)
                        hour = self.rng.randint(9, 19)
                        tx_timestamps.append(
                            base_cutoff - timedelta(days=offset_days, hours=23 - hour, minutes=self.rng.randint(0, 59))
                        )
                    # 80% de chance de recomprar nos próximos 30 dias
                    if self.rng.random() < 0.80:
                        for _ in range(self.rng.randint(1, 3)):
                            tx_timestamps.append(
                                base_cutoff + timedelta(days=self.rng.randint(3, 27), hours=self.rng.randint(10, 20))
                            )

                elif archetype == "WEEKEND_BARGAIN_HUNTER":
                    n_orders = self.rng.randint(7, 13)
                    for _ in range(n_orders):
                        offset_days = self.rng.randint(3, days_since_signup - 2)
                        candidate_dt = base_cutoff - timedelta(days=offset_days)
                        # Ajusta para cair no sábado (5) ou domingo (6) à noite (21h-23h)
                        while candidate_dt.weekday() not in (5, 6):
                            candidate_dt -= timedelta(days=1)
                        candidate_dt = candidate_dt.replace(
                            hour=self.rng.choice([21, 22, 23]),
                            minute=self.rng.randint(0, 59),
                        )
                        tx_timestamps.append(candidate_dt)
                    if self.rng.random() < 0.65:
                        tx_timestamps.append(base_cutoff + timedelta(days=self.rng.randint(4, 25)))

                elif archetype == "AT_RISK_DECELERATING":
                    # Comprava bastante há 90-250 dias, mas só 1 compra pequena há 45-75 dias
                    for _ in range(self.rng.randint(6, 10)):
                        offset_days = self.rng.randint(95, days_since_signup - 2)
                        tx_timestamps.append(
                            base_cutoff - timedelta(days=offset_days, hours=self.rng.randint(8, 21))
                        )
                    tx_timestamps.append(base_cutoff - timedelta(days=self.rng.randint(45, 75)))
                    # Baixa probabilidade de recompra nos próximos 30 dias (alto risco de churn)
                    if self.rng.random() < 0.15:
                        tx_timestamps.append(base_cutoff + timedelta(days=self.rng.randint(15, 29)))

                elif archetype == "HIBERNATING_CHURNED":
                    # Última compra há mais de 120 dias; nenhuma compra no futuro
                    for _ in range(self.rng.randint(2, 5)):
                        offset_days = self.rng.randint(125, days_since_signup - 2)
                        tx_timestamps.append(
                            base_cutoff - timedelta(days=offset_days, hours=self.rng.randint(9, 22))
                        )

                elif archetype == "RECENT_PROMISING":
                    for _ in range(self.rng.randint(3, 6)):
                        offset_days = self.rng.randint(1, days_since_signup - 1)
                        tx_timestamps.append(
                            base_cutoff - timedelta(days=offset_days, hours=self.rng.randint(10, 23))
                        )
                    if self.rng.random() < 0.75:
                        tx_timestamps.append(base_cutoff + timedelta(days=self.rng.randint(2, 22)))

                tx_timestamps.sort()

                for order_idx, ts in enumerate(tx_timestamps):
                    order_seq += 1
                    order_id = f"ORD-{order_seq:06d}"

                    if archetype == "CHAMPION_HIGH_FREQ":
                        cat_name, min_p, max_p = self.rng.choice(CATEGORIES[:4])
                        items_cnt = self.rng.randint(2, 5)
                    elif archetype == "WEEKEND_BARGAIN_HUNTER":
                        cat_name, min_p, max_p = self.rng.choice(CATEGORIES[2:])
                        items_cnt = self.rng.randint(1, 3)
                    else:
                        cat_name, min_p, max_p = self.rng.choice(CATEGORIES)
                        items_cnt = self.rng.randint(1, 4)

                    unit_val = self.rng.uniform(min_p, max_p)
                    gross = round(unit_val * items_cnt, 2)

                    # Clientes AT_RISK apresentam queda no ticket das últimas compras
                    if archetype == "AT_RISK_DECELERATING" and order_idx >= len(tx_timestamps) - 2:
                        gross = round(gross * 0.35, 2)
                    # Clientes CHAMPION apresentam aceleração no ticket das últimas compras
                    elif archetype == "CHAMPION_HIGH_FREQ" and order_idx >= len(tx_timestamps) - 3:
                        gross = round(gross * 1.35, 2)

                    if archetype == "WEEKEND_BARGAIN_HUNTER" or self.rng.random() < 0.30:
                        disc_pct = self.rng.uniform(0.08, 0.25)
                        discount = round(gross * disc_pct, 2)
                    else:
                        discount = 0.0

                    net = round(max(10.0, gross - discount), 2)
                    payment = "PIX" if self.rng.random() < 0.55 else self.rng.choice(PAYMENTS)
                    status = "COMPLETED" if self.rng.random() < 0.94 else self.rng.choice(["CANCELLED", "REFUNDED"])

                    orders_rows.append(
                        (
                            order_id,
                            customer_id,
                            ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            cat_name,
                            items_cnt,
                            gross,
                            discount,
                            net,
                            payment,
                            status,
                        )
                    )

            conn.executemany(
                "INSERT INTO customers VALUES (?, ?, ?, ?, ?)",
                customers_rows,
            )
            conn.executemany(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                orders_rows,
            )
            conn.commit()
        finally:
            conn.close()

        logger.info(
            "Base OLTP de E-Commerce gerada | clientes=%d | pedidos=%d | db=%s",
            len(customers_rows),
            len(orders_rows),
            db_path.name,
        )
        return {"customers": len(customers_rows), "orders": len(orders_rows)}
