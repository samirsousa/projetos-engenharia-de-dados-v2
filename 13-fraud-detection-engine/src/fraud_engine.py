"""
Motor Estatístico de Detecção de Anomalias e Fraudes em Transações Financeiras (Stage 2).

Implementa:
1. Cálculo de Baselines Estatísticos por Perfil (`profile_statistical_baselines`) e
   por Usuário (`user_statistical_baselines`) utilizando:
   - Média Amostral (Mean), Desvio Padrão Amostral (Std Dev), Mediana, MAD (Median Absolute Deviation),
     IQR (Intervalo Interquartil), Percentis P95/P99 e Estimador Robusto Podado (Anti-Masking).
2. Cálculo de Z-Score Paramétrico por Usuário, Modified Z-Score (Iglewicz & Hoaglin) e Z-Score de Perfil.
3. Detecção ComportamentalEspacial/Temporal:
   - Explosão de Velocidade (Velocity Burst em minutos).
   - Viagem Geograficamente Impossível (Impossible Geo-Travel via Haversine km/h).
   - Janela Noturna de Alto Risco (Madrugada 01h-05h) + Dispositivo Não Reconhecido + MCC de Risco.
4. Persistência da tabela `suspect_transactions` e matriz de avaliação (Precision, Recall, F1-Score).
"""

from __future__ import annotations

import math
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple

from src.config import (
    COMPOSITE_SUSPECT_CUTOFF,
    IMPOSSIBLE_TRAVEL_SPEED_KMH,
    MODIFIED_Z_SCORE_THRESHOLD,
    SQLITE_DB_PATH,
    VELOCITY_BURST_WINDOW_MINUTES,
    Z_SCORE_CRITICAL_THRESHOLD,
    Z_SCORE_SUSPECT_THRESHOLD,
    Z_SCORE_WARNING_THRESHOLD,
)

EARTH_RADIUS_KM = 6371.0088


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return round(2.0 * EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a))), 2)


def _percentile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return sorted_vals[lower]
    weight = pos - lower
    return sorted_vals[lower] * (1.0 - weight) + sorted_vals[upper] * weight


def compute_robust_distribution_stats(values: List[float]) -> Dict[str, float]:
    """
    Calcula métricas paramétricas e não-paramétricas robustas de uma série de valores monetários.
    Aplica filtro anti-masking baseado em MAD (3.5 * 1.4826 * MAD) para estimar a média (baseline_mean)
    e o desvio padrão (baseline_std) da operação normal sem contaminação por outliers extremos.
    """
    s_vals = sorted(values)
    n = len(s_vals)
    raw_mean = statistics.mean(s_vals)
    raw_std = statistics.stdev(s_vals) if n > 1 else 1.0

    median_val = statistics.median(s_vals)
    abs_devs = sorted(abs(x - median_val) for x in s_vals)
    mad_val = max(1.0, statistics.median(abs_devs))
    # Consistência normal do MAD: sigma_hat = 1.4826 * MAD
    robust_sigma_mad = 1.4826 * mad_val

    # Filtragem de inliers (Anti-Masking) para baseline limpo de Z-Score
    inliers = [x for x in s_vals if abs(x - median_val) <= (3.5 * robust_sigma_mad)]
    if len(inliers) >= 5:
        baseline_mean = statistics.mean(inliers)
        baseline_std = max(1.0, statistics.stdev(inliers))
    else:
        baseline_mean = median_val
        baseline_std = max(1.0, robust_sigma_mad)

    q25 = _percentile(s_vals, 0.25)
    q75 = _percentile(s_vals, 0.75)
    iqr = max(1.0, q75 - q25)
    p95 = _percentile(s_vals, 0.95)
    p99 = _percentile(s_vals, 0.99)

    return {
        "tx_count": n,
        "raw_mean_brl": round(raw_mean, 2),
        "raw_std_brl": round(raw_std, 2),
        "baseline_mean_brl": round(baseline_mean, 2),
        "baseline_std_brl": round(baseline_std, 2),
        "median_brl": round(median_val, 2),
        "mad_brl": round(mad_val, 2),
        "iqr_brl": round(iqr, 2),
        "p95_brl": round(p95, 2),
        "p99_brl": round(p99, 2),
        "upper_3sigma_limit_brl": round(baseline_mean + 3.0 * baseline_std, 2),
    }


class StatisticalFraudDetectionEngine:
    """Motor de detecção de anomalias financeiras baseado em Z-Score por usuário/perfil e heurísticas."""

    def __init__(self, db_path: Path = SQLITE_DB_PATH) -> None:
        self.db_path = db_path

    def run_detection(self) -> Dict[str, Any]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM raw_customers ORDER BY user_id")
            customers = {r["user_id"]: dict(r) for r in cur.fetchall()}

            cur.execute(
                "SELECT * FROM raw_transactions ORDER BY user_id, transaction_timestamp, transaction_id"
            )
            tx_rows = [dict(r) for r in cur.fetchall()]

            # 1. Agrupamento por Perfil e por Usuário para cálculo dos Baselines Estatísticos
            amounts_by_profile: Dict[str, List[float]] = defaultdict(list)
            amounts_by_user: Dict[str, List[float]] = defaultdict(list)
            tx_by_user: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

            for tx in tx_rows:
                amt = float(tx["amount_brl"])
                amounts_by_profile[tx["profile_code"]].append(amt)
                amounts_by_user[tx["user_id"]].append(amt)
                tx_by_user[tx["user_id"]].append(tx)

            profile_baselines: Dict[str, Dict[str, Any]] = {}
            for p_code, vals in sorted(amounts_by_profile.items()):
                stats = compute_robust_distribution_stats(vals)
                profile_baselines[p_code] = {
                    "profile_code": p_code,
                    **stats,
                }

            user_baselines: Dict[str, Dict[str, Any]] = {}
            for u_id, vals in sorted(amounts_by_user.items()):
                cust = customers[u_id]
                stats = compute_robust_distribution_stats(vals)
                user_baselines[u_id] = {
                    "user_id": u_id,
                    "full_name": cust["full_name"],
                    "profile_code": cust["profile_code"],
                    "home_city": cust["home_city"],
                    "home_uf": cust["home_uf"],
                    "declared_monthly_income_brl": cust["declared_monthly_income_brl"],
                    **stats,
                }

            # 2. Scoring de cada transação comparando contra o Baseline do Usuário e do Perfil
            scored_transactions: List[Dict[str, Any]] = []
            suspect_transactions: List[Dict[str, Any]] = []

            for u_id, user_txs in tx_by_user.items():
                u_base = user_baselines[u_id]
                p_base = profile_baselines[u_base["profile_code"]]
                cust = customers[u_id]

                prev_dt: datetime | None = None
                prev_lat: float | None = None
                prev_lon: float | None = None

                for tx in user_txs:
                    amt = float(tx["amount_brl"])
                    tx_dt = datetime.strptime(tx["transaction_timestamp"], "%Y-%m-%d %H:%M:%S")
                    tx_lat = float(tx["tx_latitude"])
                    tx_lon = float(tx["tx_longitude"])

                    # Z-Score Paramétrico do Usuário: (X - mu_baseline) / sigma_baseline
                    user_z_score = round(
                        (amt - u_base["baseline_mean_brl"]) / u_base["baseline_std_brl"], 2
                    )

                    # Modified Z-Score Robusto (Iglewicz & Hoaglin): 0.6745 * (X - Mediana) / MAD
                    user_modified_z = round(
                        (0.6745 * (amt - u_base["median_brl"])) / u_base["mad_brl"], 2
                    )

                    # Z-Score em relação ao Perfil (Peer Group)
                    profile_z_score = round(
                        (amt - p_base["baseline_mean_brl"]) / p_base["baseline_std_brl"], 2
                    )

                    # Razão Valor / Média do Usuário
                    amount_to_mean_ratio = round(amt / max(1.0, u_base["baseline_mean_brl"]), 2)

                    # Dinâmica Temporal e Geoespacial entre transações consecutivas da conta
                    if prev_dt is not None and prev_lat is not None and prev_lon is not None:
                        minutes_since_prev = round(
                            max(0.1, (tx_dt - prev_dt).total_seconds() / 60.0), 2
                        )
                        dist_from_prev_km = _haversine_km(prev_lat, prev_lon, tx_lat, tx_lon)
                        geo_velocity_kmh = round(
                            dist_from_prev_km / max(0.05, minutes_since_prev / 60.0), 2
                        )
                    else:
                        minutes_since_prev = 9999.0
                        dist_from_prev_km = _haversine_km(
                            cust["home_latitude"], cust["home_longitude"], tx_lat, tx_lon
                        )
                        geo_velocity_kmh = 0.0

                    prev_dt = tx_dt
                    prev_lat = tx_lat
                    prev_lon = tx_lon

                    # Avaliação de Regras Estatísticas e Comportamentais
                    triggered_rules: List[str] = []
                    risk_points = 0.0

                    if user_z_score >= Z_SCORE_CRITICAL_THRESHOLD:
                        triggered_rules.append(f"Z_SCORE_EXTREME(>={Z_SCORE_CRITICAL_THRESHOLD})")
                        risk_points += 52.0
                    elif user_z_score >= Z_SCORE_SUSPECT_THRESHOLD:
                        triggered_rules.append(f"Z_SCORE_3SIGMA(>={Z_SCORE_SUSPECT_THRESHOLD})")
                        risk_points += 38.0
                    elif user_z_score >= Z_SCORE_WARNING_THRESHOLD:
                        triggered_rules.append(f"Z_SCORE_WARNING(>={Z_SCORE_WARNING_THRESHOLD})")
                        risk_points += 18.0

                    if user_modified_z >= MODIFIED_Z_SCORE_THRESHOLD:
                        triggered_rules.append(f"MODIFIED_Z_MAD(>={MODIFIED_Z_SCORE_THRESHOLD})")
                        risk_points += 18.0

                    if profile_z_score >= Z_SCORE_SUSPECT_THRESHOLD:
                        triggered_rules.append("PROFILE_PEER_3SIGMA_OUTLIER")
                        risk_points += 10.0

                    if int(tx["is_trusted_device"]) == 0 and user_z_score >= 2.2:
                        triggered_rules.append("UNTRUSTED_NEW_DEVICE")
                        risk_points += 14.0

                    if int(tx["is_high_risk_mcc"]) == 1 and user_z_score >= 2.2:
                        triggered_rules.append(f"HIGH_RISK_MCC({tx['mcc_code']})")
                        risk_points += 12.0

                    if 1 <= tx_dt.hour <= 5 and int(tx["is_trusted_device"]) == 0:
                        triggered_rules.append("NIGHT_OWL_01H_05H_UNTRUSTED")
                        risk_points += 16.0

                    if minutes_since_prev <= VELOCITY_BURST_WINDOW_MINUTES and user_z_score >= 2.0:
                        triggered_rules.append(f"VELOCITY_BURST({minutes_since_prev:.1f}min)")
                        risk_points += 22.0

                    if geo_velocity_kmh >= IMPOSSIBLE_TRAVEL_SPEED_KMH and dist_from_prev_km >= 250.0:
                        triggered_rules.append(f"IMPOSSIBLE_TRAVEL({geo_velocity_kmh:.0f}km/h)")
                        risk_points += 28.0

                    composite_score = round(min(100.0, risk_points), 2)

                    # Critério de Alerta: Z-Score >= 3.0 (Regra 3-Sigma) OU Score Composto >= 50.0
                    is_suspect = (
                        1
                        if (
                            user_z_score >= Z_SCORE_SUSPECT_THRESHOLD
                            or composite_score >= COMPOSITE_SUSPECT_CUTOFF
                        )
                        else 0
                    )

                    if composite_score >= 78.0 or user_z_score >= 4.5:
                        risk_severity = "CRITICAL_FRAUD_ALERT"
                        recommended_action = "AUTO_BLOCK_AND_FREEZE_ACCOUNT"
                    elif is_suspect == 1:
                        risk_severity = "HIGH_SUSPECT_ANOMALY"
                        recommended_action = "HOLD_TX_AND_ANALYST_REVIEW"
                    elif composite_score >= 25.0 or user_z_score >= Z_SCORE_WARNING_THRESHOLD:
                        risk_severity = "MEDIUM_WATCHLIST"
                        recommended_action = "STEP_UP_BIOMETRIC_2FA"
                    else:
                        risk_severity = "LOW_NORMAL"
                        recommended_action = "ALLOW_AUTOMATICALLY"

                    enriched_row = {
                        "transaction_id": tx["transaction_id"],
                        "user_id": u_id,
                        "full_name": cust["full_name"],
                        "profile_code": tx["profile_code"],
                        "transaction_timestamp": tx["transaction_timestamp"],
                        "amount_brl": amt,
                        "user_baseline_mean_brl": u_base["baseline_mean_brl"],
                        "user_baseline_std_brl": u_base["baseline_std_brl"],
                        "user_upper_3sigma_brl": u_base["upper_3sigma_limit_brl"],
                        "user_z_score": user_z_score,
                        "user_modified_z_score": user_modified_z,
                        "profile_z_score": profile_z_score,
                        "amount_to_mean_ratio": amount_to_mean_ratio,
                        "payment_channel": tx["payment_channel"],
                        "mcc_code": tx["mcc_code"],
                        "merchant_category": tx["merchant_category"],
                        "is_high_risk_mcc": int(tx["is_high_risk_mcc"]),
                        "device_id": tx["device_id"],
                        "is_trusted_device": int(tx["is_trusted_device"]),
                        "tx_city": tx["tx_city"],
                        "tx_uf": tx["tx_uf"],
                        "minutes_since_prev_tx": minutes_since_prev,
                        "distance_from_prev_km": dist_from_prev_km,
                        "geo_velocity_kmh": geo_velocity_kmh,
                        "composite_risk_score": composite_score,
                        "is_suspect": is_suspect,
                        "risk_severity": risk_severity,
                        "recommended_action": recommended_action,
                        "triggered_rules": " | ".join(triggered_rules) if triggered_rules else "NONE",
                        "ground_truth_is_fraud": int(tx["ground_truth_is_fraud"]),
                        "injected_fraud_typology": tx["injected_fraud_typology"],
                    }

                    scored_transactions.append(enriched_row)
                    if is_suspect == 1:
                        suspect_transactions.append(enriched_row)

            # Ordena transações suspeitas pelo maior Score de Risco e maior Z-Score
            scored_transactions.sort(key=lambda r: r["transaction_id"])
            suspect_transactions.sort(
                key=lambda r: (r["composite_risk_score"], r["user_z_score"]),
                reverse=True,
            )

            # 3. Persiste as tabelas analíticas e a tabela `suspect_transactions` no SQLite
            self._persist_results(
                cur,
                list(profile_baselines.values()),
                list(user_baselines.values()),
                scored_transactions,
                suspect_transactions,
            )
            conn.commit()

            metrics = self._compute_evaluation_metrics(scored_transactions, suspect_transactions)
            return {
                "profile_baselines": list(profile_baselines.values()),
                "user_baselines": list(user_baselines.values()),
                "scored_transactions": scored_transactions,
                "suspect_transactions": suspect_transactions,
                "metrics": metrics,
            }
        finally:
            conn.close()

    def _persist_results(
        self,
        cur: sqlite3.Cursor,
        profile_baselines: List[Dict[str, Any]],
        user_baselines: List[Dict[str, Any]],
        scored_transactions: List[Dict[str, Any]],
        suspect_transactions: List[Dict[str, Any]],
    ) -> None:
        cur.executescript(
            """
            DROP TABLE IF EXISTS suspect_transactions;
            DROP TABLE IF EXISTS scored_transactions_all;
            DROP TABLE IF EXISTS user_statistical_baselines;
            DROP TABLE IF EXISTS profile_statistical_baselines;

            CREATE TABLE profile_statistical_baselines (
                profile_code TEXT PRIMARY KEY,
                tx_count INTEGER NOT NULL,
                raw_mean_brl REAL NOT NULL,
                raw_std_brl REAL NOT NULL,
                baseline_mean_brl REAL NOT NULL,
                baseline_std_brl REAL NOT NULL,
                median_brl REAL NOT NULL,
                mad_brl REAL NOT NULL,
                iqr_brl REAL NOT NULL,
                p95_brl REAL NOT NULL,
                p99_brl REAL NOT NULL,
                upper_3sigma_limit_brl REAL NOT NULL
            );

            CREATE TABLE user_statistical_baselines (
                user_id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                profile_code TEXT NOT NULL,
                home_city TEXT NOT NULL,
                home_uf TEXT NOT NULL,
                declared_monthly_income_brl REAL NOT NULL,
                tx_count INTEGER NOT NULL,
                raw_mean_brl REAL NOT NULL,
                raw_std_brl REAL NOT NULL,
                baseline_mean_brl REAL NOT NULL,
                baseline_std_brl REAL NOT NULL,
                median_brl REAL NOT NULL,
                mad_brl REAL NOT NULL,
                iqr_brl REAL NOT NULL,
                p95_brl REAL NOT NULL,
                p99_brl REAL NOT NULL,
                upper_3sigma_limit_brl REAL NOT NULL
            );

            CREATE TABLE scored_transactions_all (
                transaction_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                full_name TEXT NOT NULL,
                profile_code TEXT NOT NULL,
                transaction_timestamp TEXT NOT NULL,
                amount_brl REAL NOT NULL,
                user_baseline_mean_brl REAL NOT NULL,
                user_baseline_std_brl REAL NOT NULL,
                user_upper_3sigma_brl REAL NOT NULL,
                user_z_score REAL NOT NULL,
                user_modified_z_score REAL NOT NULL,
                profile_z_score REAL NOT NULL,
                amount_to_mean_ratio REAL NOT NULL,
                payment_channel TEXT NOT NULL,
                mcc_code TEXT NOT NULL,
                merchant_category TEXT NOT NULL,
                is_high_risk_mcc INTEGER NOT NULL,
                device_id TEXT NOT NULL,
                is_trusted_device INTEGER NOT NULL,
                tx_city TEXT NOT NULL,
                tx_uf TEXT NOT NULL,
                minutes_since_prev_tx REAL NOT NULL,
                distance_from_prev_km REAL NOT NULL,
                geo_velocity_kmh REAL NOT NULL,
                composite_risk_score REAL NOT NULL,
                is_suspect INTEGER NOT NULL,
                risk_severity TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                triggered_rules TEXT NOT NULL,
                ground_truth_is_fraud INTEGER NOT NULL,
                injected_fraud_typology TEXT NOT NULL
            );

            CREATE TABLE suspect_transactions (
                transaction_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                full_name TEXT NOT NULL,
                profile_code TEXT NOT NULL,
                transaction_timestamp TEXT NOT NULL,
                amount_brl REAL NOT NULL,
                user_baseline_mean_brl REAL NOT NULL,
                user_baseline_std_brl REAL NOT NULL,
                user_upper_3sigma_brl REAL NOT NULL,
                user_z_score REAL NOT NULL,
                user_modified_z_score REAL NOT NULL,
                profile_z_score REAL NOT NULL,
                amount_to_mean_ratio REAL NOT NULL,
                payment_channel TEXT NOT NULL,
                mcc_code TEXT NOT NULL,
                merchant_category TEXT NOT NULL,
                is_high_risk_mcc INTEGER NOT NULL,
                device_id TEXT NOT NULL,
                is_trusted_device INTEGER NOT NULL,
                tx_city TEXT NOT NULL,
                tx_uf TEXT NOT NULL,
                minutes_since_prev_tx REAL NOT NULL,
                distance_from_prev_km REAL NOT NULL,
                geo_velocity_kmh REAL NOT NULL,
                composite_risk_score REAL NOT NULL,
                is_suspect INTEGER NOT NULL,
                risk_severity TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                triggered_rules TEXT NOT NULL,
                ground_truth_is_fraud INTEGER NOT NULL,
                injected_fraud_typology TEXT NOT NULL
            );

            CREATE INDEX idx_suspect_score ON suspect_transactions(composite_risk_score DESC, user_z_score DESC);
            CREATE INDEX idx_suspect_user ON suspect_transactions(user_id, profile_code);
            """
        )

        for tbl_name, rows in (
            ("profile_statistical_baselines", profile_baselines),
            ("user_statistical_baselines", user_baselines),
            ("scored_transactions_all", scored_transactions),
            ("suspect_transactions", suspect_transactions),
        ):
            if not rows:
                continue
            cols = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT INTO {tbl_name} ({', '.join(cols)}) VALUES ({placeholders})"
            cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows])

    def _compute_evaluation_metrics(
        self,
        all_tx: List[Dict[str, Any]],
        suspect_tx: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Calcula matriz de confusão, Precision, Recall, F1-Score e impacto financeiro evitado."""
        tp = sum(1 for r in all_tx if r["is_suspect"] == 1 and r["ground_truth_is_fraud"] == 1)
        fp = sum(1 for r in all_tx if r["is_suspect"] == 1 and r["ground_truth_is_fraud"] == 0)
        fn = sum(1 for r in all_tx if r["is_suspect"] == 0 and r["ground_truth_is_fraud"] == 1)
        tn = sum(1 for r in all_tx if r["is_suspect"] == 0 and r["ground_truth_is_fraud"] == 0)

        precision = round((tp / max(1, tp + fp)) * 100.0, 2)
        recall = round((tp / max(1, tp + fn)) * 100.0, 2)
        f1_score = round(
            (2.0 * precision * recall) / max(0.01, precision + recall), 2
        )
        false_positive_rate = round((fp / max(1, fp + tn)) * 100.0, 2)

        total_volume_brl = round(sum(r["amount_brl"] for r in all_tx), 2)
        suspect_volume_brl = round(sum(r["amount_brl"] for r in suspect_tx), 2)
        prevented_fraud_loss_brl = round(
            sum(r["amount_brl"] for r in suspect_tx if r["ground_truth_is_fraud"] == 1), 2
        )
        avg_suspect_z_score = round(
            sum(r["user_z_score"] for r in suspect_tx) / max(1, len(suspect_tx)), 2
        )
        max_suspect_z_score = round(
            max((r["user_z_score"] for r in suspect_tx), default=0.0), 2
        )

        return {
            "total_transactions": len(all_tx),
            "total_suspect_flagged": len(suspect_tx),
            "alert_rate_pct": round((len(suspect_tx) / max(1, len(all_tx))) * 100.0, 2),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
            "precision_pct": precision,
            "recall_pct": recall,
            "f1_score_pct": f1_score,
            "false_positive_rate_pct": false_positive_rate,
            "total_transacted_volume_brl": total_volume_brl,
            "suspect_flagged_volume_brl": suspect_volume_brl,
            "prevented_fraud_loss_brl": prevented_fraud_loss_brl,
            "avg_suspect_z_score": avg_suspect_z_score,
            "max_suspect_z_score": max_suspect_z_score,
        }
