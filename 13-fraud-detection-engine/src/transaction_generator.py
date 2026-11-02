"""
Gerador Sintético de Base de Clientes e Transações Financeiras com Tipologias de Fraude (Stage 1).

Simula o comportamento transacional bancário e de cartões/PIX de 100 clientes segmentados em 4 perfis
(`RETAIL_BASIC`, `AFFLUENT_PLUS`, `PRIVATE_WEALTH`, `SME_CORPORATE`) ao longo de 60 dias.
Injeta 5 tipologias clássicas de fraude financeira para validação estatística (Z-Score, MAD e Regras).
"""

from __future__ import annotations

import csv
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple

from src.config import (
    CUSTOMER_PROFILES,
    HOME_CITIES,
    MERCHANT_CATEGORIES,
    PAYMENT_CHANNELS,
    RAW_TX_DIR,
    SQLITE_DB_PATH,
    ensure_directories,
)

REMOTE_FRAUD_LOCATIONS = [
    {"city": "Miami (Foreign CNP)", "uf": "EX", "lat": 25.7617, "lon": -80.1918},
    {"city": "Lagos (Foreign Gateway)", "uf": "EX", "lat": 6.5244, "lon": 3.3792},
    {"city": "Manaus (Remote Node)", "uf": "AM", "lat": -3.1190, "lon": -60.0217},
    {"city": "Fortaleza (Remote Node)", "uf": "CE", "lat": -3.7172, "lon": -38.5433},
]


def _weighted_choice(rng: random.Random, items: List[Tuple[Any, float]]) -> Any:
    total = sum(w for _, w in items)
    r = rng.uniform(0.0, total)
    acc = 0.0
    for val, weight in items:
        if acc + weight >= r:
            return val
        acc += weight
    return items[-1][0]


class FinancialTransactionSimulator:
    """Simulador estocástico de transações financeiras com baselines individuais por usuário e perfil."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_dataset(
        self, num_customers: int = 100
    ) -> Dict[str, List[Dict[str, Any]]]:
        profile_weights = [
            (code, meta["weight"]) for code, meta in CUSTOMER_PROFILES.items()
        ]
        low_risk_mccs = [m for m in MERCHANT_CATEGORIES if m["is_high_risk_mcc"] == 0]
        high_risk_mccs = [m for m in MERCHANT_CATEGORIES if m["is_high_risk_mcc"] == 1]

        customers: List[Dict[str, Any]] = []
        transactions: List[Dict[str, Any]] = []

        base_start_dt = datetime(2026, 1, 1, 8, 0, 0)
        tx_seq = 1

        for cust_idx in range(1, num_customers + 1):
            user_id = f"USR-{cust_idx:04d}"
            profile_code = _weighted_choice(self.rng, profile_weights)
            profile_meta = CUSTOMER_PROFILES[profile_code]
            home = self.rng.choice(HOME_CITIES)

            # Cada usuário possui sua própria média e desvio padrão orgânicos dentro do seu perfil
            user_latent_mean = round(
                profile_meta["mean_amount_brl"] * self.rng.uniform(0.78, 1.25), 2
            )
            user_latent_std = round(
                profile_meta["std_amount_brl"] * self.rng.uniform(0.75, 1.18), 2
            )
            trusted_device_id = f"DEV-{user_id}-TRUSTED"

            customers.append(
                {
                    "user_id": user_id,
                    "full_name": f"Cliente Bancário {cust_idx:04d}",
                    "profile_code": profile_code,
                    "profile_name": profile_meta["profile_name"],
                    "declared_monthly_income_brl": round(
                        profile_meta["monthly_income_brl"] * self.rng.uniform(0.85, 1.20), 2
                    ),
                    "home_city": home["city"],
                    "home_uf": home["uf"],
                    "home_latitude": home["lat"],
                    "home_longitude": home["lon"],
                    "trusted_device_id": trusted_device_id,
                    "account_open_date": "2024-03-15",
                }
            )

            # Número de transações normais do usuário (20 a 28 transações históricas)
            num_normal_tx = self.rng.randint(21, 28)
            current_dt = base_start_dt + timedelta(
                hours=self.rng.randint(1, 36), minutes=self.rng.randint(0, 59)
            )

            for _ in range(num_normal_tx):
                # Intervalo orgânico entre transações: 12h a 64h em horário comercial/diurno (07h às 22h)
                step_hours = self.rng.uniform(12.0, 56.0)
                current_dt = current_dt + timedelta(hours=step_hours)
                if current_dt.hour < 7:
                    current_dt = current_dt.replace(hour=self.rng.randint(8, 19))
                elif current_dt.hour >= 23:
                    current_dt = current_dt.replace(hour=self.rng.randint(9, 21))

                # Valor normal concentrado em torno de user_latent_mean (truncado dentro de +-2.1 sigma)
                z_norm = max(-1.6, min(2.05, self.rng.gauss(0.0, 0.92)))
                amount_brl = round(
                    max(12.0, user_latent_mean + z_norm * user_latent_std), 2
                )

                mcc = self.rng.choice(low_risk_mccs)
                channel = self.rng.choice(
                    ["PIX_INSTANT", "CREDIT_CARD_CHIP", "DEBIT_CONTACTLESS", "CREDIT_CARD_VIRTUAL_CNP"]
                )
                tx_lat = round(home["lat"] + self.rng.gauss(0.0, 0.03), 6)
                tx_lon = round(home["lon"] + self.rng.gauss(0.0, 0.03), 6)

                transactions.append(
                    {
                        "transaction_id": f"TXN-{tx_seq:06d}",
                        "user_id": user_id,
                        "profile_code": profile_code,
                        "transaction_timestamp": current_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "amount_brl": amount_brl,
                        "payment_channel": channel,
                        "mcc_code": mcc["mcc_code"],
                        "merchant_category": mcc["category"],
                        "is_high_risk_mcc": mcc["is_high_risk_mcc"],
                        "device_id": trusted_device_id,
                        "is_trusted_device": 1,
                        "tx_city": home["city"],
                        "tx_uf": home["uf"],
                        "tx_latitude": tx_lat,
                        "tx_longitude": tx_lon,
                        "ground_truth_is_fraud": 0,
                        "injected_fraud_typology": "NONE_LEGITIMATE",
                    }
                )
                tx_seq += 1

            # Injeção controlada de anomalias / fraudes em ~55% dos usuários (1 a 2 eventos anômalos por conta afetada)
            if self.rng.random() < 0.56:
                num_frauds = 1 if self.rng.random() < 0.78 else 2
                for f_idx in range(num_frauds):
                    typology_roll = (cust_idx + f_idx) % 5

                    if typology_roll == 0:
                        # TYP-01: Extreme Amount Z-Score Spike (Account Takeover / Limit Drain)
                        current_dt = current_dt + timedelta(hours=self.rng.uniform(6.0, 18.0))
                        spike_sigma = self.rng.uniform(4.8, 8.5)
                        fraud_amount = round(user_latent_mean + spike_sigma * user_latent_std, 2)
                        mcc = self.rng.choice(high_risk_mccs)
                        transactions.append(
                            {
                                "transaction_id": f"TXN-{tx_seq:06d}",
                                "user_id": user_id,
                                "profile_code": profile_code,
                                "transaction_timestamp": current_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                "amount_brl": fraud_amount,
                                "payment_channel": "TED_WIRE",
                                "mcc_code": mcc["mcc_code"],
                                "merchant_category": mcc["category"],
                                "is_high_risk_mcc": 1,
                                "device_id": f"DEV-UNKNOWN-{tx_seq}",
                                "is_trusted_device": 0,
                                "tx_city": home["city"],
                                "tx_uf": home["uf"],
                                "tx_latitude": round(home["lat"] + 0.02, 6),
                                "tx_longitude": round(home["lon"] + 0.02, 6),
                                "ground_truth_is_fraud": 1,
                                "injected_fraud_typology": "TYP01_EXTREME_AMOUNT_ATO_SPIKE",
                            }
                        )
                        tx_seq += 1

                    elif typology_roll == 1:
                        # TYP-02: Night-Owl PIX Drain (Madrugada 02h-04h + Dispositivo Desconhecido + Z > 3.5)
                        night_dt = (current_dt + timedelta(days=1)).replace(
                            hour=self.rng.randint(2, 4),
                            minute=self.rng.randint(5, 52),
                            second=self.rng.randint(10, 55),
                        )
                        current_dt = night_dt
                        spike_sigma = self.rng.uniform(3.8, 6.4)
                        fraud_amount = round(user_latent_mean + spike_sigma * user_latent_std, 2)
                        mcc = next(m for m in high_risk_mccs if m["mcc_code"] == "4829")
                        transactions.append(
                            {
                                "transaction_id": f"TXN-{tx_seq:06d}",
                                "user_id": user_id,
                                "profile_code": profile_code,
                                "transaction_timestamp": current_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                "amount_brl": fraud_amount,
                                "payment_channel": "PIX_INSTANT",
                                "mcc_code": mcc["mcc_code"],
                                "merchant_category": mcc["category"],
                                "is_high_risk_mcc": 1,
                                "device_id": f"DEV-EMULATOR-{tx_seq}",
                                "is_trusted_device": 0,
                                "tx_city": home["city"],
                                "tx_uf": home["uf"],
                                "tx_latitude": round(home["lat"] + 0.05, 6),
                                "tx_longitude": round(home["lon"] - 0.04, 6),
                                "ground_truth_is_fraud": 1,
                                "injected_fraud_typology": "TYP02_NIGHT_OWL_PIX_DRAIN",
                            }
                        )
                        tx_seq += 1

                    elif typology_roll == 2:
                        # TYP-03: Velocity Burst Attack (Transação em < 3 minutos após a anterior com valor atípico)
                        current_dt = current_dt + timedelta(minutes=self.rng.uniform(1.5, 4.0))
                        spike_sigma = self.rng.uniform(3.5, 5.8)
                        fraud_amount = round(user_latent_mean + spike_sigma * user_latent_std, 2)
                        mcc = self.rng.choice(high_risk_mccs)
                        transactions.append(
                            {
                                "transaction_id": f"TXN-{tx_seq:06d}",
                                "user_id": user_id,
                                "profile_code": profile_code,
                                "transaction_timestamp": current_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                "amount_brl": fraud_amount,
                                "payment_channel": "CREDIT_CARD_VIRTUAL_CNP",
                                "mcc_code": mcc["mcc_code"],
                                "merchant_category": mcc["category"],
                                "is_high_risk_mcc": 1,
                                "device_id": f"DEV-BOTNET-{tx_seq}",
                                "is_trusted_device": 0,
                                "tx_city": home["city"],
                                "tx_uf": home["uf"],
                                "tx_latitude": round(home["lat"] + 0.01, 6),
                                "tx_longitude": round(home["lon"] + 0.01, 6),
                                "ground_truth_is_fraud": 1,
                                "injected_fraud_typology": "TYP03_HIGH_VELOCITY_BURST_ATTACK",
                            }
                        )
                        tx_seq += 1

                    elif typology_roll == 3:
                        # TYP-04: Impossible Travel Geo-Velocity (> 2.000 km em 20 minutos + valor elevado)
                        current_dt = current_dt + timedelta(minutes=self.rng.uniform(15.0, 28.0))
                        remote = self.rng.choice(REMOTE_FRAUD_LOCATIONS)
                        spike_sigma = self.rng.uniform(3.4, 5.5)
                        fraud_amount = round(user_latent_mean + spike_sigma * user_latent_std, 2)
                        mcc = self.rng.choice(high_risk_mccs)
                        transactions.append(
                            {
                                "transaction_id": f"TXN-{tx_seq:06d}",
                                "user_id": user_id,
                                "profile_code": profile_code,
                                "transaction_timestamp": current_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                "amount_brl": fraud_amount,
                                "payment_channel": "CREDIT_CARD_CHIP",
                                "mcc_code": mcc["mcc_code"],
                                "merchant_category": mcc["category"],
                                "is_high_risk_mcc": 1,
                                "device_id": f"DEV-POS-FOREIGN-{tx_seq}",
                                "is_trusted_device": 0,
                                "tx_city": remote["city"],
                                "tx_uf": remote["uf"],
                                "tx_latitude": remote["lat"],
                                "tx_longitude": remote["lon"],
                                "ground_truth_is_fraud": 1,
                                "injected_fraud_typology": "TYP04_IMPOSSIBLE_GEO_TRAVEL",
                            }
                        )
                        tx_seq += 1

                    else:
                        # TYP-05: High-Risk Crypto/Luxury Profile Outlier
                        current_dt = current_dt + timedelta(hours=self.rng.uniform(4.0, 11.0))
                        spike_sigma = self.rng.uniform(4.1, 7.2)
                        fraud_amount = round(user_latent_mean + spike_sigma * user_latent_std, 2)
                        mcc = next(m for m in high_risk_mccs if m["mcc_code"] == "6051")
                        transactions.append(
                            {
                                "transaction_id": f"TXN-{tx_seq:06d}",
                                "user_id": user_id,
                                "profile_code": profile_code,
                                "transaction_timestamp": current_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                "amount_brl": fraud_amount,
                                "payment_channel": "PIX_INSTANT",
                                "mcc_code": mcc["mcc_code"],
                                "merchant_category": mcc["category"],
                                "is_high_risk_mcc": 1,
                                "device_id": f"DEV-WEB-PROXY-{tx_seq}",
                                "is_trusted_device": 0,
                                "tx_city": home["city"],
                                "tx_uf": home["uf"],
                                "tx_latitude": round(home["lat"] + 0.02, 6),
                                "tx_longitude": round(home["lon"] - 0.02, 6),
                                "ground_truth_is_fraud": 1,
                                "injected_fraud_typology": "TYP05_CRYPTO_EXCHANGE_OUTLIER",
                            }
                        )
                        tx_seq += 1

        # Ordena globalmente as transações por timestamp e reatribui IDs sequenciais cronológicos
        transactions.sort(key=lambda x: x["transaction_timestamp"])
        for idx, tx in enumerate(transactions, start=1):
            tx["transaction_id"] = f"TXN-{idx:06d}"

        return {
            "raw_customers": customers,
            "raw_transactions": transactions,
        }


def save_raw_transactions_and_load_db(
    dataset: Dict[str, List[Dict[str, Any]]],
    raw_dir: Path = RAW_TX_DIR,
    db_path: Path = SQLITE_DB_PATH,
) -> Dict[str, int]:
    """Salva os CSVs brutos em `data/raw_transactions/` e carrega as tabelas `raw_*` no SQLite."""
    ensure_directories()
    raw_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    for name, rows in dataset.items():
        if not rows:
            continue
        csv_path = raw_dir / f"{name}.csv"
        fieldnames = list(rows[0].keys())
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            PRAGMA foreign_keys = ON;

            DROP TABLE IF EXISTS raw_transactions;
            DROP TABLE IF EXISTS raw_customers;

            CREATE TABLE raw_customers (
                user_id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                profile_code TEXT NOT NULL,
                profile_name TEXT NOT NULL,
                declared_monthly_income_brl REAL NOT NULL,
                home_city TEXT NOT NULL,
                home_uf TEXT NOT NULL,
                home_latitude REAL NOT NULL,
                home_longitude REAL NOT NULL,
                trusted_device_id TEXT NOT NULL,
                account_open_date TEXT NOT NULL
            );

            CREATE TABLE raw_transactions (
                transaction_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                profile_code TEXT NOT NULL,
                transaction_timestamp TEXT NOT NULL,
                amount_brl REAL NOT NULL,
                payment_channel TEXT NOT NULL,
                mcc_code TEXT NOT NULL,
                merchant_category TEXT NOT NULL,
                is_high_risk_mcc INTEGER NOT NULL,
                device_id TEXT NOT NULL,
                is_trusted_device INTEGER NOT NULL,
                tx_city TEXT NOT NULL,
                tx_uf TEXT NOT NULL,
                tx_latitude REAL NOT NULL,
                tx_longitude REAL NOT NULL,
                ground_truth_is_fraud INTEGER NOT NULL,
                injected_fraud_typology TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES raw_customers(user_id)
            );

            CREATE INDEX idx_raw_tx_user ON raw_transactions(user_id, transaction_timestamp);
            CREATE INDEX idx_raw_tx_profile ON raw_transactions(profile_code);
            """
        )

        counts: Dict[str, int] = {}
        for tbl in ("raw_customers", "raw_transactions"):
            rows = dataset[tbl]
            cols = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT INTO {tbl} ({', '.join(cols)}) VALUES ({placeholders})"
            cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
            counts[tbl] = len(rows)

        conn.commit()
        return counts
    finally:
        conn.close()
