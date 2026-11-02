"""
Gerador Sintético de Dados de Assinaturas SaaS B2B (OLTP & Ledger Mensal de MRR).

Simula o ciclo de vida realista de clientes de assinatura ao longo de 12 safras (coortes)
mensais (2025-01 a 2025-12), modelando:
- Curva de sobrevivência de Weibull/Exponencial (maior risco nos primeiros 90 dias - Onboarding Cliff,
  seguido de estabilização para clientes maduros).
- Movimentações de Receita Recorrente Mensal (MRR Bridge):
  NEW, RETAINED, EXPANSION (Upsell/Add-on seats), CONTRACTION (Downgrade) e CHURNED.
- Diferenciação entre Churn Voluntário e Involuntário (falha de cobrança), planos e canais de aquisição.
"""

from __future__ import annotations

import csv
import random
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple

from src.config import (
    ACQUISITION_CHANNELS,
    CHURN_REASONS,
    RAW_OLTP_DIR,
    SAAS_PLANS,
    SQLITE_DB_PATH,
    ensure_directories,
)

INDUSTRIES = [
    "Fintech & Financial Services",
    "E-Commerce & Retail Tech",
    "Healthtech & Clinics",
    "Logistics & Supply Chain",
    "B2B SaaS & Software",
    "Agribusiness & FoodTech",
    "Education & EdTech",
]

REGIONS_BR = [
    ("SP", "Sudeste", 0.44),
    ("RJ", "Sudeste", 0.13),
    ("MG", "Sudeste", 0.11),
    ("PR", "Sul", 0.09),
    ("RS", "Sul", 0.08),
    ("SC", "Sul", 0.08),
    ("DF", "Centro-Oeste", 0.07),
]


def _generate_months(start_year: int = 2025, num_months: int = 12) -> List[str]:
    """Gera lista ordenada de meses no formato YYYY-MM."""
    months: List[str] = []
    year, month = start_year, 1
    for _ in range(num_months):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _month_first_day(ym: str) -> str:
    return f"{ym}-01"


def _month_last_day(ym: str) -> str:
    year, month = map(int, ym.split("-"))
    if month in (1, 3, 5, 7, 8, 10, 12):
        day = 31
    elif month in (4, 6, 9, 11):
        day = 30
    else:
        day = 28
    return f"{year:04d}-{month:02d}-{day:02d}"


def _weighted_choice(rng: random.Random, items: List[Tuple[Any, float]]) -> Any:
    total = sum(w for _, w in items)
    r = rng.uniform(0, total)
    upto = 0.0
    for item, weight in items:
        if upto + weight >= r:
            return item
        upto += weight
    return items[-1][0]


class SaaSSubscriptionSimulator:
    """Simulador estocástico determinístico (com seed fixa) de ciclo de vida de assinaturas SaaS."""

    def __init__(self, seed: int = 42, start_year: int = 2025, horizon_months: int = 12) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.months = _generate_months(start_year=start_year, num_months=horizon_months)

    def generate_dataset(
        self, base_customers_per_cohort: int = 75
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Gera as 4 tabelas fundamentais do ecossistema de assinaturas:
        1. raw_plans
        2. raw_customers
        3. raw_subscriptions
        4. raw_mrr_ledger
        """
        plans_rows: List[Dict[str, Any]] = list(SAAS_PLANS.values())
        customers_rows: List[Dict[str, Any]] = []
        subscriptions_rows: List[Dict[str, Any]] = []
        mrr_ledger_rows: List[Dict[str, Any]] = []

        channel_weights = [(ch, meta["weight"]) for ch, meta in ACQUISITION_CHANNELS.items()]
        region_weights = [((uf, macro), w) for uf, macro, w in REGIONS_BR]
        reason_weights = [((reason, ctype), w) for reason, ctype, w in CHURN_REASONS]

        cust_seq = 1
        sub_seq = 1
        ledger_seq = 1

        for cohort_idx, cohort_month in enumerate(self.months):
            # Crescimento orgânico na aquisição de clientes ao longo do ano + sazonalidade
            growth_factor = 1.0 + (cohort_idx * 0.035)
            cohort_size = int(round(base_customers_per_cohort * growth_factor))

            for _ in range(cohort_size):
                customer_id = f"CUST-{cust_seq:05d}"
                subscription_id = f"SUB-{sub_seq:05d}"
                cust_seq += 1
                sub_seq += 1

                channel = _weighted_choice(self.rng, channel_weights)
                channel_meta = ACQUISITION_CHANNELS[channel]

                # Escolha do plano condicionada ao canal (Outbound traz mais Enterprise/Growth)
                if channel == "Outbound Sales (SDR/AE)":
                    plan_id = _weighted_choice(
                        self.rng,
                        [("PLN-STARTER", 0.15), ("PLN-GROWTH", 0.50), ("PLN-ENTERPRISE", 0.35)],
                    )
                elif channel in ("Partner & Referral", "Organic Search (SEO)"):
                    plan_id = _weighted_choice(
                        self.rng,
                        [("PLN-STARTER", 0.52), ("PLN-GROWTH", 0.36), ("PLN-ENTERPRISE", 0.12)],
                    )
                else:
                    plan_id = _weighted_choice(
                        self.rng,
                        [("PLN-STARTER", 0.64), ("PLN-GROWTH", 0.28), ("PLN-ENTERPRISE", 0.08)],
                    )

                plan_meta = SAAS_PLANS[plan_id]
                segment = (
                    "SMB"
                    if plan_id == "PLN-STARTER"
                    else ("Mid-Market" if plan_id == "PLN-GROWTH" else "Enterprise")
                )

                uf, macro_region = _weighted_choice(self.rng, region_weights)
                industry = self.rng.choice(INDUSTRIES)

                # Ciclo de cobrança: planos maiores preferem ciclo anual
                annual_prob = 0.22 if plan_id == "PLN-STARTER" else (0.40 if plan_id == "PLN-GROWTH" else 0.62)
                billing_cycle = "ANNUAL" if self.rng.random() < annual_prob else "MONTHLY"

                # CAC com leve variação individual por complexidade de venda
                cac_multiplier = 1.35 if segment == "Enterprise" else (1.05 if segment == "Mid-Market" else 0.85)
                cac_brl = round(
                    channel_meta["cac_brl"] * cac_multiplier * self.rng.uniform(0.88, 1.14), 2
                )

                signup_day = self.rng.randint(1, 28)
                signup_date = f"{cohort_month}-{signup_day:02d}"

                # MRR inicial contratado (com variações de assentos extras ou desconto anual)
                extra_seats_factor = self.rng.choice([1.0, 1.0, 1.10, 1.20, 1.35])
                discount_factor = (1.0 - plan_meta["annual_discount_pct"]) if billing_cycle == "ANNUAL" else 1.0
                initial_mrr = round(plan_meta["base_mrr_brl"] * extra_seats_factor * discount_factor, 2)

                customers_rows.append(
                    {
                        "customer_id": customer_id,
                        "company_name": f"ClientCorp {cust_seq - 1:04d} Ltda",
                        "segment": segment,
                        "industry": industry,
                        "state_uf": uf,
                        "macro_region": macro_region,
                        "acquisition_channel": channel,
                        "cac_brl": cac_brl,
                        "signup_date": signup_date,
                        "cohort_month": cohort_month,
                    }
                )

                # Simula a trajetória mês a mês da assinatura a partir de cohort_idx até o fim do horizonte
                current_mrr = initial_mrr
                current_plan_id = plan_id
                is_active = True
                churn_date: str | None = None
                churn_reason_str: str | None = None
                churn_type_str: str | None = None
                tenure_months = 0

                for month_idx in range(cohort_idx, len(self.months)):
                    snapshot_month = self.months[month_idx]
                    months_since_signup = month_idx - cohort_idx
                    cur_plan_meta = SAAS_PLANS[current_plan_id]

                    if months_since_signup == 0:
                        # Mês 0 (Aquisição): Todo cliente adquirido entra ativo como NEW MRR
                        tenure_months += 1
                        health_score = round(self.rng.uniform(62.0, 96.0), 1)
                        tickets = self.rng.choices([0, 1, 2, 3, 4], weights=[45, 30, 15, 7, 3])[0]
                        gross_profit = round(current_mrr * cur_plan_meta["gross_margin_pct"], 2)

                        mrr_ledger_rows.append(
                            {
                                "ledger_id": f"LDG-{ledger_seq:06d}",
                                "subscription_id": subscription_id,
                                "customer_id": customer_id,
                                "cohort_month": cohort_month,
                                "snapshot_month": snapshot_month,
                                "months_since_signup": months_since_signup,
                                "plan_id": current_plan_id,
                                "billing_cycle": billing_cycle,
                                "previous_mrr_brl": 0.0,
                                "current_mrr_brl": current_mrr,
                                "mrr_delta_brl": current_mrr,
                                "movement_type": "NEW",
                                "active_flag": 1,
                                "gross_profit_brl": gross_profit,
                                "usage_health_score": health_score,
                                "support_tickets_month": tickets,
                            }
                        )
                        ledger_seq += 1
                        continue

                    if not is_active:
                        break

                    # Avalia risco de Churn no mês t > 0
                    # Curva hazard: meses 1, 2 e 3 (Onboarding Cliff) têm risco mais elevado; após mês 6 cai
                    if months_since_signup in (1, 2):
                        tenure_hazard = 1.45
                    elif months_since_signup == 3:
                        tenure_hazard = 1.20
                    elif months_since_signup <= 6:
                        tenure_hazard = 0.92
                    else:
                        tenure_hazard = 0.68

                    cycle_hazard = 0.52 if billing_cycle == "ANNUAL" else 1.12
                    effective_churn_prob = (
                        cur_plan_meta["base_monthly_churn_prob"]
                        * channel_meta["churn_multiplier"]
                        * tenure_hazard
                        * cycle_hazard
                    )

                    roll = self.rng.random()
                    previous_mrr = current_mrr

                    if roll < effective_churn_prob:
                        # Ocorreu CHURN neste mês
                        is_active = False
                        current_mrr = 0.0
                        churn_date = _month_last_day(snapshot_month)
                        churn_reason_str, churn_type_str = _weighted_choice(self.rng, reason_weights)
                        health_score = round(self.rng.uniform(18.0, 48.0), 1)
                        tickets = self.rng.choices([1, 2, 3, 5, 7], weights=[20, 25, 25, 20, 10])[0]

                        mrr_ledger_rows.append(
                            {
                                "ledger_id": f"LDG-{ledger_seq:06d}",
                                "subscription_id": subscription_id,
                                "customer_id": customer_id,
                                "cohort_month": cohort_month,
                                "snapshot_month": snapshot_month,
                                "months_since_signup": months_since_signup,
                                "plan_id": current_plan_id,
                                "billing_cycle": billing_cycle,
                                "previous_mrr_brl": previous_mrr,
                                "current_mrr_brl": 0.0,
                                "mrr_delta_brl": round(-previous_mrr, 2),
                                "movement_type": "CHURNED",
                                "active_flag": 0,
                                "gross_profit_brl": 0.0,
                                "usage_health_score": health_score,
                                "support_tickets_month": tickets,
                            }
                        )
                        ledger_seq += 1
                        break

                    # Cliente permaneceu ativo: verifica Expansão (Upsell / Seat Expansion) ou Contração
                    tenure_months += 1
                    exp_prob = cur_plan_meta["expansion_prob"]
                    con_prob = cur_plan_meta["contraction_prob"]
                    rev_roll = self.rng.random()

                    if rev_roll < exp_prob:
                        # Expansão de MRR (+15% a +45%, ou upgrade de plano)
                        if current_plan_id == "PLN-STARTER" and self.rng.random() < 0.45:
                            current_plan_id = "PLN-GROWTH"
                            current_mrr = round(max(previous_mrr * 1.40, SAAS_PLANS["PLN-GROWTH"]["base_mrr_brl"]), 2)
                        elif current_plan_id == "PLN-GROWTH" and self.rng.random() < 0.30:
                            current_plan_id = "PLN-ENTERPRISE"
                            current_mrr = round(max(previous_mrr * 1.55, SAAS_PLANS["PLN-ENTERPRISE"]["base_mrr_brl"] * 0.85), 2)
                        else:
                            expansion_factor = self.rng.uniform(1.12, 1.32)
                            current_mrr = round(previous_mrr * expansion_factor, 2)
                        movement_type = "EXPANSION"
                        health_score = round(self.rng.uniform(78.0, 99.0), 1)
                    elif rev_roll < (exp_prob + con_prob):
                        # Contração de MRR (-10% a -25%)
                        contraction_factor = self.rng.uniform(0.76, 0.90)
                        current_mrr = round(max(99.0, previous_mrr * contraction_factor), 2)
                        movement_type = "CONTRACTION"
                        health_score = round(self.rng.uniform(45.0, 68.0), 1)
                    else:
                        movement_type = "RETAINED"
                        health_score = round(self.rng.uniform(65.0, 94.0), 1)

                    cur_plan_meta = SAAS_PLANS[current_plan_id]
                    mrr_delta = round(current_mrr - previous_mrr, 2)
                    gross_profit = round(current_mrr * cur_plan_meta["gross_margin_pct"], 2)
                    tickets = self.rng.choices([0, 1, 2, 3], weights=[55, 28, 12, 5])[0]

                    mrr_ledger_rows.append(
                        {
                            "ledger_id": f"LDG-{ledger_seq:06d}",
                            "subscription_id": subscription_id,
                            "customer_id": customer_id,
                            "cohort_month": cohort_month,
                            "snapshot_month": snapshot_month,
                            "months_since_signup": months_since_signup,
                            "plan_id": current_plan_id,
                            "billing_cycle": billing_cycle,
                            "previous_mrr_brl": previous_mrr,
                            "current_mrr_brl": current_mrr,
                            "mrr_delta_brl": mrr_delta,
                            "movement_type": movement_type,
                            "active_flag": 1,
                            "gross_profit_brl": gross_profit,
                            "usage_health_score": health_score,
                            "support_tickets_month": tickets,
                        }
                    )
                    ledger_seq += 1

                subscriptions_rows.append(
                    {
                        "subscription_id": subscription_id,
                        "customer_id": customer_id,
                        "initial_plan_id": plan_id,
                        "current_plan_id": current_plan_id,
                        "billing_cycle": billing_cycle,
                        "start_date": signup_date,
                        "end_date": churn_date or "",
                        "status": "ACTIVE" if is_active else "CHURNED",
                        "churn_type": churn_type_str or "Active (No Churn)",
                        "churn_reason": churn_reason_str or "Active (No Churn)",
                        "initial_mrr_brl": initial_mrr,
                        "final_mrr_brl": current_mrr,
                        "tenure_months": tenure_months,
                    }
                )

        return {
            "raw_plans": plans_rows,
            "raw_customers": customers_rows,
            "raw_subscriptions": subscriptions_rows,
            "raw_mrr_ledger": mrr_ledger_rows,
        }


def save_raw_csvs(dataset: Dict[str, List[Dict[str, Any]]], output_dir: Path = RAW_OLTP_DIR) -> Dict[str, Path]:
    """Salva as tabelas brutas geradas em arquivos CSV no diretório raw_oltp."""
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: Dict[str, Path] = {}

    for table_name, rows in dataset.items():
        if not rows:
            continue
        csv_path = output_dir / f"{table_name}.csv"
        fieldnames = list(rows[0].keys())
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        saved_paths[table_name] = csv_path

    return saved_paths


def load_into_sqlite(dataset: Dict[str, List[Dict[str, Any]]], db_path: Path = SQLITE_DB_PATH) -> Dict[str, int]:
    """Cria o schema relacional SQLite e carrega todas as tabelas OLTP e de Ledger MRR."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            PRAGMA foreign_keys = ON;

            DROP TABLE IF EXISTS raw_mrr_ledger;
            DROP TABLE IF EXISTS raw_subscriptions;
            DROP TABLE IF EXISTS raw_customers;
            DROP TABLE IF EXISTS raw_plans;

            CREATE TABLE raw_plans (
                plan_id TEXT PRIMARY KEY,
                plan_name TEXT NOT NULL,
                tier_level INTEGER NOT NULL,
                base_mrr_brl REAL NOT NULL,
                annual_discount_pct REAL NOT NULL,
                base_monthly_churn_prob REAL NOT NULL,
                expansion_prob REAL NOT NULL,
                contraction_prob REAL NOT NULL,
                gross_margin_pct REAL NOT NULL,
                included_seats INTEGER NOT NULL
            );

            CREATE TABLE raw_customers (
                customer_id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                segment TEXT NOT NULL,
                industry TEXT NOT NULL,
                state_uf TEXT NOT NULL,
                macro_region TEXT NOT NULL,
                acquisition_channel TEXT NOT NULL,
                cac_brl REAL NOT NULL,
                signup_date TEXT NOT NULL,
                cohort_month TEXT NOT NULL
            );

            CREATE TABLE raw_subscriptions (
                subscription_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                initial_plan_id TEXT NOT NULL,
                current_plan_id TEXT NOT NULL,
                billing_cycle TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT,
                status TEXT NOT NULL,
                churn_type TEXT NOT NULL,
                churn_reason TEXT NOT NULL,
                initial_mrr_brl REAL NOT NULL,
                final_mrr_brl REAL NOT NULL,
                tenure_months INTEGER NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES raw_customers(customer_id),
                FOREIGN KEY (initial_plan_id) REFERENCES raw_plans(plan_id),
                FOREIGN KEY (current_plan_id) REFERENCES raw_plans(plan_id)
            );

            CREATE TABLE raw_mrr_ledger (
                ledger_id TEXT PRIMARY KEY,
                subscription_id TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                cohort_month TEXT NOT NULL,
                snapshot_month TEXT NOT NULL,
                months_since_signup INTEGER NOT NULL,
                plan_id TEXT NOT NULL,
                billing_cycle TEXT NOT NULL,
                previous_mrr_brl REAL NOT NULL,
                current_mrr_brl REAL NOT NULL,
                mrr_delta_brl REAL NOT NULL,
                movement_type TEXT NOT NULL,
                active_flag INTEGER NOT NULL,
                gross_profit_brl REAL NOT NULL,
                usage_health_score REAL NOT NULL,
                support_tickets_month INTEGER NOT NULL,
                FOREIGN KEY (subscription_id) REFERENCES raw_subscriptions(subscription_id),
                FOREIGN KEY (customer_id) REFERENCES raw_customers(customer_id),
                FOREIGN KEY (plan_id) REFERENCES raw_plans(plan_id)
            );

            CREATE INDEX idx_ledger_snapshot ON raw_mrr_ledger(snapshot_month, movement_type);
            CREATE INDEX idx_ledger_cohort ON raw_mrr_ledger(cohort_month, months_since_signup);
            CREATE INDEX idx_cust_cohort ON raw_customers(cohort_month, segment);
            """
        )

        counts: Dict[str, int] = {}
        for table_name in ("raw_plans", "raw_customers", "raw_subscriptions", "raw_mrr_ledger"):
            rows = dataset[table_name]
            cols = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"
            cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
            counts[table_name] = len(rows)

        conn.commit()
        return counts
    finally:
        conn.close()
