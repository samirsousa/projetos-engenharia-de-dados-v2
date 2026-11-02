"""
Motor de Engenharia de Features Preditivas (Point-in-Time Correct Feature Computation).

Calcula vetores de features avançadas por cliente (`customer_id`) a partir das transações OLTP:
1. RFM (Recência, Frequência Total/30d/90d, Valor Monetário Total/30d/90d, Quintis 1-5 e Segmento).
2. Ticket Médio Móvel (Lifetime AOV, Rolling AOV últimas 3 compras, Rolling AOV 30d/90d, Momentum e CV).
3. Sazonalidade e Cadência Comportamental (Razão Fim de Semana, Compras Noturnas, Codificação Cíclica
   Seno/Cosseno de Horário, Intervalo Médio Inter-Compras, Índice de Atraso de Cadência e Entropia de Shannon).
4. Labels Supervisionadas Anti-Leakage (`target_churn_30d` e `target_next_30d_spend`).
"""

from __future__ import annotations

import math
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.config import FeatureStoreConfig, setup_logger

logger = setup_logger("Feature-Engineering")


@dataclass
class CustomerFeatureVector:
    """Vetor completo de features da Camada Gold para um cliente em um instante `as_of_timestamp`."""

    # Identificação e Contexto Temporal (Entity + Point-in-Time Key)
    customer_id: str
    as_of_timestamp: str
    state_uf: str
    acquisition_channel: str
    tenure_days: int

    # 1. Bloco RFM (Recency, Frequency, Monetary)
    rfm_recency_days: float
    rfm_frequency_total: int
    rfm_frequency_30d: int
    rfm_frequency_90d: int
    rfm_monetary_total: float
    rfm_monetary_30d: float
    rfm_monetary_90d: float
    rfm_r_score: int
    rfm_f_score: int
    rfm_m_score: int
    rfm_composite_score: float
    rfm_segment: str

    # 2. Bloco Ticket Médio Móvel, Volatilidade e Momentum
    aov_lifetime: float
    rolling_aov_last_3: float
    rolling_aov_30d: float
    rolling_aov_90d: float
    aov_momentum_ratio: float
    ticket_stddev: float
    ticket_cv: float
    avg_items_per_order: float

    # 3. Bloco Sazonalidade, Cadência Temporal e Entropia Comportamental
    weekend_purchase_ratio: float
    night_purchase_ratio: float
    peak_hour_sin: float
    peak_hour_cos: float
    dominant_quarter: str
    avg_interpurchase_days: float
    stddev_interpurchase_days: float
    overdue_cadence_ratio: float
    category_shannon_entropy: float
    distinct_categories_count: int
    discount_usage_rate: float
    avg_discount_depth_pct: float
    pix_payment_share: float
    cancellation_rate: float

    # 4. Variáveis Alvo Supervisionadas (Holdout Pós-Cutoff para Treino ML)
    target_churn_30d: int
    target_next_30d_spend: float


class FeatureEngineeringPipeline:
    """Calcula features analíticas com garantia Point-in-Time (Zero Data Leakage)."""

    def __init__(self, config: Optional[FeatureStoreConfig] = None) -> None:
        self.config = config or FeatureStoreConfig()
        self.config.ensure_directories()

    @staticmethod
    def _parse_iso_utc(ts_str: str) -> datetime:
        cleaned = ts_str.strip()
        if len(cleaned) == 10:
            return datetime.strptime(cleaned, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        return datetime.fromisoformat(cleaned)

    @staticmethod
    def _mean(values: Sequence[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    @classmethod
    def _stddev(cls, values: Sequence[float]) -> float:
        if len(values) < 2:
            return 0.0
        avg = cls._mean(values)
        variance = sum((x - avg) ** 2 for x in values) / len(values)
        return math.sqrt(variance)

    @staticmethod
    def _shannon_entropy(items: Sequence[str]) -> float:
        """Calcula a Entropia de Shannon H(X) = -sum(p_i * log2(p_i)) da cesta de categorias."""
        total = len(items)
        if total <= 1:
            return 0.0
        counts = Counter(items)
        entropy = 0.0
        for cnt in counts.values():
            prob = cnt / total
            if prob > 0:
                entropy -= prob * math.log2(prob)
        return round(entropy, 4)

    @staticmethod
    def _assign_quintile_scores(
        values: List[float], higher_is_better: bool = True
    ) -> List[int]:
        """Atribui escores de quintil de 1 a 5 baseados no ranking empírico da distribuição."""
        n = len(values)
        if n == 0:
            return []
        indexed = sorted(enumerate(values), key=lambda pair: pair[1], reverse=not higher_is_better)
        scores = [1] * n
        for rank_idx, (orig_idx, _) in enumerate(indexed):
            percentile = rank_idx / max(1, n - 1)
            score = min(5, max(1, int(percentile * 5) + 1))
            scores[orig_idx] = score
        return scores

    @staticmethod
    def _classify_rfm_segment(r_score: int, f_score: int, m_score: int) -> str:
        """Classifica a persona de marketing/CRM a partir dos escores R, F e M."""
        if r_score >= 4 and f_score >= 4 and m_score >= 4:
            return "CHAMPIONS"
        if r_score >= 3 and f_score >= 3 and m_score >= 3:
            return "LOYAL_CUSTOMERS"
        if r_score >= 4 and f_score >= 2:
            return "POTENTIAL_LOYALIST"
        if r_score == 2 or (r_score <= 2 and f_score >= 3):
            return "AT_RISK"
        return "HIBERNATING"

    def compute_customer_features(
        self,
        as_of_timestamp: Optional[str] = None,
        label_horizon_days: Optional[int] = None,
    ) -> List[CustomerFeatureVector]:
        """
        Extrai as transações do banco OLTP e computa todas as features respeitando
        estritamente a janela temporal `order_timestamp <= as_of_timestamp`.
        """
        cutoff_str = as_of_timestamp or self.config.default_as_of_date
        horizon_days = label_horizon_days or self.config.default_label_horizon_days

        cutoff_dt = self._parse_iso_utc(cutoff_str)
        window_30d_start = cutoff_dt - timedelta(days=30)
        window_90d_start = cutoff_dt - timedelta(days=90)
        label_window_end = cutoff_dt + timedelta(days=horizon_days)

        logger.info(
            "Calculando vetores de features Point-in-Time | as_of=%s | label_horizon=%dd",
            cutoff_str,
            horizon_days,
        )

        conn = sqlite3.connect(str(self.config.oltp_db_path))
        conn.row_factory = sqlite3.Row
        try:
            customers = [
                dict(r)
                for r in conn.execute("SELECT * FROM customers ORDER BY customer_id ASC").fetchall()
            ]
            all_orders = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM orders ORDER BY customer_id ASC, order_timestamp ASC"
                ).fetchall()
            ]
        finally:
            conn.close()

        orders_by_customer: Dict[str, List[Dict[str, Any]]] = {
            str(c["customer_id"]): [] for c in customers
        }
        for order in all_orders:
            cid = str(order["customer_id"])
            if cid in orders_by_customer:
                orders_by_customer[cid].append(order)

        intermediate_rows: List[Dict[str, Any]] = []

        for cust in customers:
            cid = str(cust["customer_id"])
            signup_dt = self._parse_iso_utc(str(cust["signup_date"]))
            tenure_days = max(1, int((cutoff_dt - signup_dt).total_seconds() // 86400))

            cust_orders = orders_by_customer.get(cid, [])

            # Separa estritamente histórico passado (<= cutoff) da janela futura de label (> cutoff)
            past_all_orders = []
            past_completed_orders = []
            future_completed_orders = []

            for ord_row in cust_orders:
                ord_dt = self._parse_iso_utc(str(ord_row["order_timestamp"]))
                ord_row["_dt"] = ord_dt
                if ord_dt <= cutoff_dt:
                    past_all_orders.append(ord_row)
                    if ord_row["order_status"] == "COMPLETED":
                        past_completed_orders.append(ord_row)
                elif cutoff_dt < ord_dt <= label_window_end:
                    if ord_row["order_status"] == "COMPLETED":
                        future_completed_orders.append(ord_row)

            # 1. Cálculos RFM Brutos
            if past_completed_orders:
                last_order_dt = past_completed_orders[-1]["_dt"]
                recency_days = round(
                    max(0.0, (cutoff_dt - last_order_dt).total_seconds() / 86400.0), 2
                )
            else:
                recency_days = float(tenure_days)

            freq_total = len(past_completed_orders)
            orders_30d = [o for o in past_completed_orders if o["_dt"] >= window_30d_start]
            orders_90d = [o for o in past_completed_orders if o["_dt"] >= window_90d_start]
            freq_30d = len(orders_30d)
            freq_90d = len(orders_90d)

            net_amounts = [float(o["net_amount"]) for o in past_completed_orders]
            monetary_total = round(sum(net_amounts), 2)
            monetary_30d = round(sum(float(o["net_amount"]) for o in orders_30d), 2)
            monetary_90d = round(sum(float(o["net_amount"]) for o in orders_90d), 2)

            # 2. Ticket Médio Móvel (Rolling AOV) e Volatilidade
            aov_lifetime = round(self._mean(net_amounts), 2)
            last_3_amounts = net_amounts[-3:] if net_amounts else []
            rolling_aov_last_3 = round(self._mean(last_3_amounts), 2)
            rolling_aov_30d = round(self._mean([float(o["net_amount"]) for o in orders_30d]), 2)
            rolling_aov_90d = round(self._mean([float(o["net_amount"]) for o in orders_90d]), 2)

            aov_momentum = (
                round(rolling_aov_last_3 / aov_lifetime, 4) if aov_lifetime > 0 else 0.0
            )
            ticket_std = round(self._stddev(net_amounts), 2)
            ticket_cv = round(ticket_std / aov_lifetime, 4) if aov_lifetime > 0 else 0.0
            avg_items = round(
                self._mean([float(o["items_count"]) for o in past_completed_orders]), 2
            )

            # 3. Sazonalidade, Cadência Temporal e Entropia Comportamental
            if freq_total > 0:
                weekend_cnt = sum(
                    1 for o in past_completed_orders if o["_dt"].weekday() in (5, 6)
                )
                night_cnt = sum(
                    1 for o in past_completed_orders if (o["_dt"].hour >= 20 or o["_dt"].hour < 6)
                )
                weekend_ratio = round(weekend_cnt / freq_total, 4)
                night_ratio = round(night_cnt / freq_total, 4)

                # Média circular/trigonométrica do horário de compra
                sin_sum = sum(
                    math.sin(2.0 * math.pi * (o["_dt"].hour + o["_dt"].minute / 60.0) / 24.0)
                    for o in past_completed_orders
                )
                cos_sum = sum(
                    math.cos(2.0 * math.pi * (o["_dt"].hour + o["_dt"].minute / 60.0) / 24.0)
                    for o in past_completed_orders
                )
                peak_hour_sin = round(sin_sum / freq_total, 4)
                peak_hour_cos = round(cos_sum / freq_total, 4)

                quarters = [f"Q{((o['_dt'].month - 1) // 3) + 1}" for o in past_completed_orders]
                dominant_quarter = Counter(quarters).most_common(1)[0][0]
            else:
                weekend_ratio = 0.0
                night_ratio = 0.0
                peak_hour_sin = 0.0
                peak_hour_cos = 1.0
                dominant_quarter = "N/A"

            # Intervalos inter-compra (em dias)
            if freq_total >= 2:
                gaps_days = [
                    max(
                        0.01,
                        (past_completed_orders[i]["_dt"] - past_completed_orders[i - 1]["_dt"]).total_seconds()
                        / 86400.0,
                    )
                    for i in range(1, freq_total)
                ]
                avg_gap = round(self._mean(gaps_days), 2)
                std_gap = round(self._stddev(gaps_days), 2)
            else:
                avg_gap = float(tenure_days)
                std_gap = 0.0

            overdue_ratio = round(recency_days / max(1.0, avg_gap), 4)

            categories_bought = [str(o["product_category"]) for o in past_completed_orders]
            cat_entropy = self._shannon_entropy(categories_bought)
            distinct_cats = len(set(categories_bought))

            if freq_total > 0:
                discounted_orders = sum(
                    1 for o in past_completed_orders if float(o["discount_amount"]) > 0
                )
                discount_rate = round(discounted_orders / freq_total, 4)
                discount_depths = [
                    float(o["discount_amount"]) / float(o["gross_amount"])
                    for o in past_completed_orders
                    if float(o["gross_amount"]) > 0
                ]
                avg_disc_depth = round(self._mean(discount_depths) * 100.0, 2)
                pix_cnt = sum(1 for o in past_completed_orders if o["payment_method"] == "PIX")
                pix_share = round(pix_cnt / freq_total, 4)
            else:
                discount_rate = 0.0
                avg_disc_depth = 0.0
                pix_share = 0.0

            total_attempted = len(past_all_orders)
            cancelled_cnt = sum(1 for o in past_all_orders if o["order_status"] != "COMPLETED")
            cancel_rate = round(cancelled_cnt / total_attempted, 4) if total_attempted > 0 else 0.0

            # 4. Targets Supervisionados (Janela Futura de 30 dias pós-cutoff)
            target_churn = 1 if len(future_completed_orders) == 0 else 0
            target_spend = round(
                sum(float(o["net_amount"]) for o in future_completed_orders), 2
            )

            intermediate_rows.append(
                {
                    "customer_id": cid,
                    "as_of_timestamp": cutoff_str,
                    "state_uf": str(cust["state_uf"]),
                    "acquisition_channel": str(cust["acquisition_channel"]),
                    "tenure_days": tenure_days,
                    "rfm_recency_days": recency_days,
                    "rfm_frequency_total": freq_total,
                    "rfm_frequency_30d": freq_30d,
                    "rfm_frequency_90d": freq_90d,
                    "rfm_monetary_total": monetary_total,
                    "rfm_monetary_30d": monetary_30d,
                    "rfm_monetary_90d": monetary_90d,
                    "aov_lifetime": aov_lifetime,
                    "rolling_aov_last_3": rolling_aov_last_3,
                    "rolling_aov_30d": rolling_aov_30d,
                    "rolling_aov_90d": rolling_aov_90d,
                    "aov_momentum_ratio": aov_momentum,
                    "ticket_stddev": ticket_std,
                    "ticket_cv": ticket_cv,
                    "avg_items_per_order": avg_items,
                    "weekend_purchase_ratio": weekend_ratio,
                    "night_purchase_ratio": night_ratio,
                    "peak_hour_sin": peak_hour_sin,
                    "peak_hour_cos": peak_hour_cos,
                    "dominant_quarter": dominant_quarter,
                    "avg_interpurchase_days": avg_gap,
                    "stddev_interpurchase_days": std_gap,
                    "overdue_cadence_ratio": overdue_ratio,
                    "category_shannon_entropy": cat_entropy,
                    "distinct_categories_count": distinct_cats,
                    "discount_usage_rate": discount_rate,
                    "avg_discount_depth_pct": avg_disc_depth,
                    "pix_payment_share": pix_share,
                    "cancellation_rate": cancel_rate,
                    "target_churn_30d": target_churn,
                    "target_next_30d_spend": target_spend,
                }
            )

        # Calcula escores de quintil RFM (1..5) em toda a coorte
        r_scores = self._assign_quintile_scores(
            [float(r["rfm_recency_days"]) for r in intermediate_rows], higher_is_better=False
        )
        f_scores = self._assign_quintile_scores(
            [float(r["rfm_frequency_total"]) for r in intermediate_rows], higher_is_better=True
        )
        m_scores = self._assign_quintile_scores(
            [float(r["rfm_monetary_total"]) for r in intermediate_rows], higher_is_better=True
        )

        feature_vectors: List[CustomerFeatureVector] = []
        for idx, row in enumerate(intermediate_rows):
            r_sc = r_scores[idx]
            f_sc = f_scores[idx]
            m_sc = m_scores[idx]
            comp_score = round((0.35 * r_sc) + (0.35 * f_sc) + (0.30 * m_sc), 2)
            segment = self._classify_rfm_segment(r_sc, f_sc, m_sc)

            feature_vectors.append(
                CustomerFeatureVector(
                    customer_id=row["customer_id"],
                    as_of_timestamp=row["as_of_timestamp"],
                    state_uf=row["state_uf"],
                    acquisition_channel=row["acquisition_channel"],
                    tenure_days=row["tenure_days"],
                    rfm_recency_days=row["rfm_recency_days"],
                    rfm_frequency_total=row["rfm_frequency_total"],
                    rfm_frequency_30d=row["rfm_frequency_30d"],
                    rfm_frequency_90d=row["rfm_frequency_90d"],
                    rfm_monetary_total=row["rfm_monetary_total"],
                    rfm_monetary_30d=row["rfm_monetary_30d"],
                    rfm_monetary_90d=row["rfm_monetary_90d"],
                    rfm_r_score=r_sc,
                    rfm_f_score=f_sc,
                    rfm_m_score=m_sc,
                    rfm_composite_score=comp_score,
                    rfm_segment=segment,
                    aov_lifetime=row["aov_lifetime"],
                    rolling_aov_last_3=row["rolling_aov_last_3"],
                    rolling_aov_30d=row["rolling_aov_30d"],
                    rolling_aov_90d=row["rolling_aov_90d"],
                    aov_momentum_ratio=row["aov_momentum_ratio"],
                    ticket_stddev=row["ticket_stddev"],
                    ticket_cv=row["ticket_cv"],
                    avg_items_per_order=row["avg_items_per_order"],
                    weekend_purchase_ratio=row["weekend_purchase_ratio"],
                    night_purchase_ratio=row["night_purchase_ratio"],
                    peak_hour_sin=row["peak_hour_sin"],
                    peak_hour_cos=row["peak_hour_cos"],
                    dominant_quarter=row["dominant_quarter"],
                    avg_interpurchase_days=row["avg_interpurchase_days"],
                    stddev_interpurchase_days=row["stddev_interpurchase_days"],
                    overdue_cadence_ratio=row["overdue_cadence_ratio"],
                    category_shannon_entropy=row["category_shannon_entropy"],
                    distinct_categories_count=row["distinct_categories_count"],
                    discount_usage_rate=row["discount_usage_rate"],
                    avg_discount_depth_pct=row["avg_discount_depth_pct"],
                    pix_payment_share=row["pix_payment_share"],
                    cancellation_rate=row["cancellation_rate"],
                    target_churn_30d=row["target_churn_30d"],
                    target_next_30d_spend=row["target_next_30d_spend"],
                )
            )

        logger.info("Engenharia de Features concluída | vetores_gerados=%d | features_por_cliente=37", len(feature_vectors))
        return feature_vectors
