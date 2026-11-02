"""
Construtor de Modelagem Dimensional (Star Schema) e Consolidador de Satisfação / NPS para Dashboard (Stage 3).

Constrói e persiste no SQLite (`sentiment_analytics_dw.db`) e exporta em CSV + Apache Parquet (`data/dashboard_mart/`):
1. Tabelas Dimensão (`dim_calendar`, `dim_products`, `dim_channels`, `dim_customers_geo`)
2. Tabela Fato (`fact_sentiment_engagement`)
3. Tabelas Mart Consolidadas prontas para Dashboard Analítico:
   - `mart_category_satisfaction_nps` (NPS simulado, proporção de sentimentos positivos/neutros/negativos e engajamento por categoria de produto)
   - `mart_product_sentiment_ranking` (Desempenho por SKU)
   - `mart_channel_engagement_performance` (Engajamento e sentimento por canal social)
   - `mart_lexicon_term_impact` (Termos do dicionário PT-BR mais frequentes nas avaliações)
"""

from __future__ import annotations

import csv
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

import pandas as pd

from src.config import (
    DASHBOARD_MART_DIR,
    PRODUCT_CATALOG,
    PTBR_SENTIMENT_LEXICON,
    REPORTS_DIR,
    SOCIAL_CHANNELS,
    SQLITE_DB_PATH,
    ensure_directories,
)

WEEKDAYS_PT = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}


class DimensionalSentimentBuilder:
    """Estrutura o Star Schema e consolida KPIs de Sentimento, NPS e Engajamento."""

    def __init__(self, db_path: Path = SQLITE_DB_PATH) -> None:
        self.db_path = db_path

    def build_and_persist(
        self, enriched_reviews: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        ensure_directories()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        dim_calendar = self._build_dim_calendar(enriched_reviews)
        dim_products = [
            {
                "product_id": p["product_id"],
                "product_name": p["product_name"],
                "category_id": p["category_id"],
                "category_name": p["category_name"],
                "brand_tier": p["brand_tier"],
                "unit_price_brl": p["unit_price_brl"],
            }
            for p in PRODUCT_CATALOG
        ]
        dim_channels = [
            {
                "channel_id": c["channel_id"],
                "channel_name": c["channel_name"],
                "platform_type": c["platform_type"],
            }
            for c in SOCIAL_CHANNELS
        ]
        dim_customers_geo = self._build_dim_customers(enriched_reviews)

        mart_category = self._build_mart_category_satisfaction(enriched_reviews)
        mart_product = self._build_mart_product_ranking(enriched_reviews)
        mart_channel = self._build_mart_channel_performance(enriched_reviews)
        mart_lexicon = self._build_mart_lexicon_terms(enriched_reviews)

        tables = {
            "dim_calendar": dim_calendar,
            "dim_products": dim_products,
            "dim_channels": dim_channels,
            "dim_customers_geo": dim_customers_geo,
            "fact_sentiment_engagement": enriched_reviews,
            "mart_category_satisfaction_nps": mart_category,
            "mart_product_sentiment_ranking": mart_product,
            "mart_channel_engagement_performance": mart_channel,
            "mart_lexicon_term_impact": mart_lexicon,
        }

        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.executescript(
                """
                PRAGMA foreign_keys = ON;

                DROP TABLE IF EXISTS mart_lexicon_term_impact;
                DROP TABLE IF EXISTS mart_channel_engagement_performance;
                DROP TABLE IF EXISTS mart_product_sentiment_ranking;
                DROP TABLE IF EXISTS mart_category_satisfaction_nps;
                DROP TABLE IF EXISTS fact_sentiment_engagement;
                DROP TABLE IF EXISTS dim_customers_geo;
                DROP TABLE IF EXISTS dim_channels;
                DROP TABLE IF EXISTS dim_products;
                DROP TABLE IF EXISTS dim_calendar;

                CREATE TABLE dim_calendar (
                    date_key TEXT PRIMARY KEY,
                    year INTEGER NOT NULL,
                    month INTEGER NOT NULL,
                    year_month TEXT NOT NULL,
                    day_of_week_pt TEXT NOT NULL,
                    is_weekend INTEGER NOT NULL
                );

                CREATE TABLE dim_products (
                    product_id TEXT PRIMARY KEY,
                    product_name TEXT NOT NULL,
                    category_id TEXT NOT NULL,
                    category_name TEXT NOT NULL,
                    brand_tier TEXT NOT NULL,
                    unit_price_brl REAL NOT NULL
                );

                CREATE TABLE dim_channels (
                    channel_id TEXT PRIMARY KEY,
                    channel_name TEXT NOT NULL,
                    platform_type TEXT NOT NULL
                );

                CREATE TABLE dim_customers_geo (
                    customer_id TEXT PRIMARY KEY,
                    author_handle TEXT NOT NULL,
                    customer_uf TEXT NOT NULL
                );

                CREATE TABLE fact_sentiment_engagement (
                    review_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    author_handle TEXT NOT NULL,
                    customer_uf TEXT NOT NULL,
                    verified_purchase INTEGER NOT NULL,
                    review_timestamp TEXT NOT NULL,
                    date_key TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    category_id TEXT NOT NULL,
                    category_name TEXT NOT NULL,
                    brand_tier TEXT NOT NULL,
                    unit_price_brl REAL NOT NULL,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT NOT NULL,
                    platform_type TEXT NOT NULL,
                    raw_review_text TEXT NOT NULL,
                    cleaned_review_text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    hashtags_extracted TEXT NOT NULL,
                    raw_polarity_sum REAL NOT NULL,
                    compound_sentiment_score REAL NOT NULL,
                    sentiment_label TEXT NOT NULL,
                    nps_score INTEGER NOT NULL,
                    nps_segment TEXT NOT NULL,
                    negation_detected_flag INTEGER NOT NULL,
                    intensifier_detected_flag INTEGER NOT NULL,
                    matched_lexicon_terms TEXT NOT NULL,
                    impressions INTEGER NOT NULL,
                    likes_count INTEGER NOT NULL,
                    comments_count INTEGER NOT NULL,
                    shares_count INTEGER NOT NULL,
                    saves_count INTEGER NOT NULL,
                    total_interactions INTEGER NOT NULL,
                    weighted_engagement_score INTEGER NOT NULL,
                    engagement_rate_pct REAL NOT NULL,
                    viral_impact_index REAL NOT NULL,
                    FOREIGN KEY (date_key) REFERENCES dim_calendar(date_key),
                    FOREIGN KEY (product_id) REFERENCES dim_products(product_id),
                    FOREIGN KEY (channel_id) REFERENCES dim_channels(channel_id),
                    FOREIGN KEY (customer_id) REFERENCES dim_customers_geo(customer_id)
                );

                CREATE TABLE mart_category_satisfaction_nps (
                    category_id TEXT PRIMARY KEY,
                    category_name TEXT NOT NULL,
                    total_reviews INTEGER NOT NULL,
                    positive_count INTEGER NOT NULL,
                    neutral_count INTEGER NOT NULL,
                    negative_count INTEGER NOT NULL,
                    positive_ratio_pct REAL NOT NULL,
                    neutral_ratio_pct REAL NOT NULL,
                    negative_ratio_pct REAL NOT NULL,
                    net_sentiment_balance_pct REAL NOT NULL,
                    promoters_count INTEGER NOT NULL,
                    passives_count INTEGER NOT NULL,
                    detractors_count INTEGER NOT NULL,
                    promoters_pct REAL NOT NULL,
                    detractors_pct REAL NOT NULL,
                    simulated_nps_score REAL NOT NULL,
                    nps_quality_zone TEXT NOT NULL,
                    avg_compound_polarity REAL NOT NULL,
                    total_impressions INTEGER NOT NULL,
                    total_interactions INTEGER NOT NULL,
                    avg_engagement_rate_pct REAL NOT NULL
                );

                CREATE TABLE mart_product_sentiment_ranking (
                    product_id TEXT PRIMARY KEY,
                    product_name TEXT NOT NULL,
                    category_name TEXT NOT NULL,
                    unit_price_brl REAL NOT NULL,
                    total_reviews INTEGER NOT NULL,
                    positive_ratio_pct REAL NOT NULL,
                    neutral_ratio_pct REAL NOT NULL,
                    negative_ratio_pct REAL NOT NULL,
                    simulated_nps_score REAL NOT NULL,
                    avg_compound_polarity REAL NOT NULL,
                    avg_engagement_rate_pct REAL NOT NULL
                );

                CREATE TABLE mart_channel_engagement_performance (
                    channel_id TEXT PRIMARY KEY,
                    channel_name TEXT NOT NULL,
                    platform_type TEXT NOT NULL,
                    total_reviews INTEGER NOT NULL,
                    total_impressions INTEGER NOT NULL,
                    total_interactions INTEGER NOT NULL,
                    avg_weighted_engagement REAL NOT NULL,
                    avg_engagement_rate_pct REAL NOT NULL,
                    positive_ratio_pct REAL NOT NULL,
                    negative_ratio_pct REAL NOT NULL,
                    simulated_nps_score REAL NOT NULL
                );

                CREATE TABLE mart_lexicon_term_impact (
                    lexicon_term TEXT PRIMARY KEY,
                    polarity_orientation TEXT NOT NULL,
                    base_lexicon_weight REAL NOT NULL,
                    occurrences_count INTEGER NOT NULL,
                    share_of_mentions_pct REAL NOT NULL
                );

                CREATE INDEX idx_fact_cat_sent ON fact_sentiment_engagement(category_id, sentiment_label);
                CREATE INDEX idx_fact_chan ON fact_sentiment_engagement(channel_id, nps_segment);
                CREATE INDEX idx_fact_date ON fact_sentiment_engagement(date_key);
                """
            )

            counts: Dict[str, int] = {}
            for tbl_name, rows in tables.items():
                if not rows:
                    counts[tbl_name] = 0
                    continue
                cols = list(rows[0].keys())
                placeholders = ", ".join(["?"] * len(cols))
                sql = f"INSERT INTO {tbl_name} ({', '.join(cols)}) VALUES ({placeholders})"
                cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
                counts[tbl_name] = len(rows)

            conn.commit()
            global_kpis = self._compute_global_kpis(enriched_reviews)
            return {
                "tables": tables,
                "table_counts": counts,
                "global_kpis": global_kpis,
            }
        finally:
            conn.close()

    def _build_dim_calendar(self, reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique_dates = sorted({r["date_key"] for r in reviews})
        rows: List[Dict[str, Any]] = []
        for dk in unique_dates:
            dt = datetime.strptime(dk, "%Y-%m-%d")
            rows.append(
                {
                    "date_key": dk,
                    "year": dt.year,
                    "month": dt.month,
                    "year_month": dk[:7],
                    "day_of_week_pt": WEEKDAYS_PT[dt.weekday()],
                    "is_weekend": 1 if dt.weekday() >= 5 else 0,
                }
            )
        return rows

    def _build_dim_customers(self, reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        by_cust: Dict[str, Dict[str, Any]] = {}
        for r in reviews:
            cid = r["customer_id"]
            if cid not in by_cust:
                by_cust[cid] = {
                    "customer_id": cid,
                    "author_handle": r["author_handle"],
                    "customer_uf": r["customer_uf"],
                }
        return [by_cust[k] for k in sorted(by_cust.keys())]

    def _build_mart_category_satisfaction(
        self, reviews: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in reviews:
            grouped[r["category_id"]].append(r)

        rows: List[Dict[str, Any]] = []
        for cat_id, items in grouped.items():
            n = len(items)
            pos = sum(1 for x in items if x["sentiment_label"] == "POSITIVE")
            neu = sum(1 for x in items if x["sentiment_label"] == "NEUTRAL")
            neg = sum(1 for x in items if x["sentiment_label"] == "NEGATIVE")

            pos_pct = round((pos / n) * 100.0, 2)
            neu_pct = round((neu / n) * 100.0, 2)
            neg_pct = round((neg / n) * 100.0, 2)
            net_sent_pct = round(pos_pct - neg_pct, 2)

            promoters = sum(1 for x in items if x["nps_segment"] == "PROMOTER")
            passives = sum(1 for x in items if x["nps_segment"] == "PASSIVE")
            detractors = sum(1 for x in items if x["nps_segment"] == "DETRACTOR")

            prom_pct = round((promoters / n) * 100.0, 2)
            det_pct = round((detractors / n) * 100.0, 2)
            nps_score = round(prom_pct - det_pct, 2)

            if nps_score >= 50.0:
                nps_zone = "Zona de Excelência (NPS >= 50)"
            elif nps_score >= 25.0:
                nps_zone = "Zona de Qualidade (25 a 49)"
            elif nps_score >= 0.0:
                nps_zone = "Zona de Aperfeiçoamento (0 a 24)"
            else:
                nps_zone = "Zona Crítica (NPS < 0 - Ação Imediata)"

            avg_polarity = round(
                sum(x["compound_sentiment_score"] for x in items) / n, 4
            )
            tot_imp = sum(x["impressions"] for x in items)
            tot_int = sum(x["total_interactions"] for x in items)
            avg_eng_pct = round(sum(x["engagement_rate_pct"] for x in items) / n, 2)

            rows.append(
                {
                    "category_id": cat_id,
                    "category_name": items[0]["category_name"],
                    "total_reviews": n,
                    "positive_count": pos,
                    "neutral_count": neu,
                    "negative_count": neg,
                    "positive_ratio_pct": pos_pct,
                    "neutral_ratio_pct": neu_pct,
                    "negative_ratio_pct": neg_pct,
                    "net_sentiment_balance_pct": net_sent_pct,
                    "promoters_count": promoters,
                    "passives_count": passives,
                    "detractors_count": detractors,
                    "promoters_pct": prom_pct,
                    "detractors_pct": det_pct,
                    "simulated_nps_score": nps_score,
                    "nps_quality_zone": nps_zone,
                    "avg_compound_polarity": avg_polarity,
                    "total_impressions": tot_imp,
                    "total_interactions": tot_int,
                    "avg_engagement_rate_pct": avg_eng_pct,
                }
            )

        rows.sort(key=lambda r: r["simulated_nps_score"], reverse=True)
        return rows

    def _build_mart_product_ranking(
        self, reviews: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in reviews:
            grouped[r["product_id"]].append(r)

        rows: List[Dict[str, Any]] = []
        for pid, items in grouped.items():
            n = len(items)
            pos_pct = round(
                (sum(1 for x in items if x["sentiment_label"] == "POSITIVE") / n) * 100.0, 2
            )
            neu_pct = round(
                (sum(1 for x in items if x["sentiment_label"] == "NEUTRAL") / n) * 100.0, 2
            )
            neg_pct = round(
                (sum(1 for x in items if x["sentiment_label"] == "NEGATIVE") / n) * 100.0, 2
            )
            prom_pct = (sum(1 for x in items if x["nps_segment"] == "PROMOTER") / n) * 100.0
            det_pct = (sum(1 for x in items if x["nps_segment"] == "DETRACTOR") / n) * 100.0
            nps_score = round(prom_pct - det_pct, 2)

            rows.append(
                {
                    "product_id": pid,
                    "product_name": items[0]["product_name"],
                    "category_name": items[0]["category_name"],
                    "unit_price_brl": items[0]["unit_price_brl"],
                    "total_reviews": n,
                    "positive_ratio_pct": pos_pct,
                    "neutral_ratio_pct": neu_pct,
                    "negative_ratio_pct": neg_pct,
                    "simulated_nps_score": nps_score,
                    "avg_compound_polarity": round(
                        sum(x["compound_sentiment_score"] for x in items) / n, 4
                    ),
                    "avg_engagement_rate_pct": round(
                        sum(x["engagement_rate_pct"] for x in items) / n, 2
                    ),
                }
            )

        rows.sort(key=lambda r: r["simulated_nps_score"], reverse=True)
        return rows

    def _build_mart_channel_performance(
        self, reviews: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in reviews:
            grouped[r["channel_id"]].append(r)

        rows: List[Dict[str, Any]] = []
        for cid, items in grouped.items():
            n = len(items)
            pos_pct = round(
                (sum(1 for x in items if x["sentiment_label"] == "POSITIVE") / n) * 100.0, 2
            )
            neg_pct = round(
                (sum(1 for x in items if x["sentiment_label"] == "NEGATIVE") / n) * 100.0, 2
            )
            prom_pct = (sum(1 for x in items if x["nps_segment"] == "PROMOTER") / n) * 100.0
            det_pct = (sum(1 for x in items if x["nps_segment"] == "DETRACTOR") / n) * 100.0

            rows.append(
                {
                    "channel_id": cid,
                    "channel_name": items[0]["channel_name"],
                    "platform_type": items[0]["platform_type"],
                    "total_reviews": n,
                    "total_impressions": sum(x["impressions"] for x in items),
                    "total_interactions": sum(x["total_interactions"] for x in items),
                    "avg_weighted_engagement": round(
                        sum(x["weighted_engagement_score"] for x in items) / n, 1
                    ),
                    "avg_engagement_rate_pct": round(
                        sum(x["engagement_rate_pct"] for x in items) / n, 2
                    ),
                    "positive_ratio_pct": pos_pct,
                    "negative_ratio_pct": neg_pct,
                    "simulated_nps_score": round(prom_pct - det_pct, 2),
                }
            )

        rows.sort(key=lambda r: r["total_interactions"], reverse=True)
        return rows

    def _build_mart_lexicon_terms(
        self, reviews: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        counter: Counter[str] = Counter()
        for r in reviews:
            terms_str = r["matched_lexicon_terms"]
            if not terms_str:
                continue
            for t in terms_str.split(", "):
                clean_t = t.lstrip("#")
                if clean_t:
                    counter[clean_t] += 1

        total_mentions = max(1, sum(counter.values()))
        rows: List[Dict[str, Any]] = []
        for term, cnt in counter.most_common(35):
            base_w = PTBR_SENTIMENT_LEXICON.get(term, 0.0)
            orientation = (
                "POSITIVE_TERM"
                if base_w > 0.4
                else ("NEGATIVE_TERM" if base_w < -0.4 else "NEUTRAL_TERM")
            )
            rows.append(
                {
                    "lexicon_term": term,
                    "polarity_orientation": orientation,
                    "base_lexicon_weight": base_w,
                    "occurrences_count": cnt,
                    "share_of_mentions_pct": round((cnt / total_mentions) * 100.0, 2),
                }
            )
        return rows

    def _compute_global_kpis(self, reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = max(1, len(reviews))
        pos = sum(1 for x in reviews if x["sentiment_label"] == "POSITIVE")
        neu = sum(1 for x in reviews if x["sentiment_label"] == "NEUTRAL")
        neg = sum(1 for x in reviews if x["sentiment_label"] == "NEGATIVE")

        promoters = sum(1 for x in reviews if x["nps_segment"] == "PROMOTER")
        passives = sum(1 for x in reviews if x["nps_segment"] == "PASSIVE")
        detractors = sum(1 for x in reviews if x["nps_segment"] == "DETRACTOR")

        prom_pct = (promoters / n) * 100.0
        det_pct = (detractors / n) * 100.0
        global_nps = round(prom_pct - det_pct, 2)

        return {
            "total_reviews": len(reviews),
            "positive_count": pos,
            "neutral_count": neu,
            "negative_count": neg,
            "positive_ratio_pct": round((pos / n) * 100.0, 2),
            "neutral_ratio_pct": round((neu / n) * 100.0, 2),
            "negative_ratio_pct": round((neg / n) * 100.0, 2),
            "promoters_count": promoters,
            "passives_count": passives,
            "detractors_count": detractors,
            "global_simulated_nps": global_nps,
            "avg_compound_polarity": round(
                sum(x["compound_sentiment_score"] for x in reviews) / n, 4
            ),
            "negation_handled_reviews": sum(x["negation_detected_flag"] for x in reviews),
            "intensifier_handled_reviews": sum(
                x["intensifier_detected_flag"] for x in reviews
            ),
            "total_impressions": sum(x["impressions"] for x in reviews),
            "total_interactions": sum(x["total_interactions"] for x in reviews),
            "avg_engagement_rate_pct": round(
                sum(x["engagement_rate_pct"] for x in reviews) / n, 2
            ),
        }


def export_dashboard_marts_and_report(
    build_results: Dict[str, Any],
    mart_dir: Path = DASHBOARD_MART_DIR,
    report_path: Path = REPORTS_DIR / "sentiment_engagement_executive_report.md",
) -> Dict[str, str]:
    """Exporta todas as tabelas dimensionais, fato e marts em CSV e Parquet, além do relatório Markdown."""
    ensure_directories()
    mart_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    exported: Dict[str, str] = {}
    for tbl_name, rows in build_results["tables"].items():
        if not rows:
            continue
        csv_path = mart_dir / f"{tbl_name}.csv"
        parquet_path = mart_dir / f"{tbl_name}.parquet"

        fieldnames = list(rows[0].keys())
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        pd.DataFrame(rows).to_parquet(parquet_path, index=False)
        exported[f"{tbl_name}_csv"] = str(csv_path)
        exported[f"{tbl_name}_parquet"] = str(parquet_path)

    k = build_results["global_kpis"]
    cat_rows = build_results["tables"]["mart_category_satisfaction_nps"]
    prod_rows = build_results["tables"]["mart_product_sentiment_ranking"]
    chan_rows = build_results["tables"]["mart_channel_engagement_performance"]
    lex_rows = build_results["tables"]["mart_lexicon_term_impact"]

    lines = [
        "# Relatório Executivo: Social Media Sentiment, Engajamento & NPS Analytics (PT-BR)",
        "",
        "## 1. Sumário Executivo Global de Satisfação e Engajamento",
        "",
        "| Indicador Analítico (NLP & Social Analytics) | Valor Consolidado | Observação Técnica |",
        "| :--- | ---: | :--- |",
        f"| **Total de Avaliações Processadas (JSON)** | `{k['total_reviews']:,}` | Textos limpos e tokenizados em PT-BR |",
        f"| **Proporção de Sentimentos Positivos** | **`{k['positive_ratio_pct']:.2f}%`** (`{k['positive_count']:,}`) | Compound Polarity `>= +0.15` |",
        f"| **Proporção de Sentimentos Neutros** | `{k['neutral_ratio_pct']:.2f}%` (`{k['neutral_count']:,}`) | Compound Polarity em `(-0.15, +0.15)` |",
        f"| **Proporção de Sentimentos Negativos** | **`{k['negative_ratio_pct']:.2f}%`** (`{k['negative_count']:,}`) | Compound Polarity `<= -0.15` |",
        f"| **NPS Simulado Global (Net Promoter Score)** | **`{k['global_simulated_nps']:+.2f}`** | Promotores: `{k['promoters_count']}` / Detratores: `{k['detractors_count']}` |",
        f"| **Polaridade Composta Média** | `{k['avg_compound_polarity']:+.4f}` | Escala normalizada `[-1.0, +1.0]` |",
        f"| **Avaliações com Inversão por Negação (`não/nunca`)** | `{k['negation_handled_reviews']:,}` | Tratadas por janela contextual de 3 tokens |",
        f"| **Alcance Total (Impressões nas Redes)** | `{k['total_impressions']:,}` | Soma nos 5 canais sociais/reviews |",
        f"| **Total de Interações (Likes/Comments/Shares/Saves)** | `{k['total_interactions']:,}` | Taxa Média de Engajamento: `{k['avg_engagement_rate_pct']:.2f}%` |",
        "",
        "---",
        "",
        "## 2. Consolidação por Categoria de Produto (`mart_category_satisfaction_nps`)",
        "",
        "| Categoria ID | Categoria de Produto | Reviews | % Positivo | % Neutro | % Negativo | Saldo Líquido | % Promotores | % Detratores | NPS Simulado | Zona de Qualidade NPS | Taxa Engajamento % |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | ---: |",
    ]

    for c in cat_rows:
        lines.append(
            f"| `{c['category_id']}` | **{c['category_name']}** | {c['total_reviews']} | "
            f"`{c['positive_ratio_pct']:.1f}%` | `{c['neutral_ratio_pct']:.1f}%` | "
            f"`{c['negative_ratio_pct']:.1f}%` | `{c['net_sentiment_balance_pct']:+.1f}%` | "
            f"{c['promoters_pct']:.1f}% | {c['detractors_pct']:.1f}% | "
            f"**`{c['simulated_nps_score']:+.1f}`** | {c['nps_quality_zone']} | `{c['avg_engagement_rate_pct']:.2f}%` |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Ranking de Sentimento e NPS por Produto SKU (`mart_product_sentiment_ranking`)",
            "",
            "| SKU ID | Produto | Categoria | Preço (R$) | Reviews | % Positivo | % Negativo | NPS Simulado | Polaridade Média | Engajamento % |",
            "| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for p in prod_rows:
        lines.append(
            f"| `{p['product_id']}` | **{p['product_name']}** | {p['category_name']} | "
            f"{p['unit_price_brl']:,.2f} | {p['total_reviews']} | "
            f"`{p['positive_ratio_pct']:.1f}%` | `{p['negative_ratio_pct']:.1f}%` | "
            f"**`{p['simulated_nps_score']:+.1f}`** | `{p['avg_compound_polarity']:+.3f}` | "
            f"`{p['avg_engagement_rate_pct']:.2f}%` |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Desempenho por Canal Social / Plataforma (`mart_channel_engagement_performance`)",
            "",
            "| Canal ID | Plataforma / Canal | Tipo | Reviews | Impressões | Interações | Engajamento Ponderado | Taxa Engajamento % | % Positivo | % Negativo | NPS Simulado |",
            "| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for ch in chan_rows:
        lines.append(
            f"| `{ch['channel_id']}` | **{ch['channel_name']}** | {ch['platform_type']} | "
            f"{ch['total_reviews']} | {ch['total_impressions']:,} | {ch['total_interactions']:,} | "
            f"{ch['avg_weighted_engagement']:,.1f} | **`{ch['avg_engagement_rate_pct']:.2f}%`** | "
            f"`{ch['positive_ratio_pct']:.1f}%` | `{ch['negative_ratio_pct']:.1f}%` | **`{ch['simulated_nps_score']:+.1f}`** |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 5. Top 15 Termos do Léxico de Polaridade PT-BR Extraídos (`mart_lexicon_term_impact`)",
            "",
            "| Termo Normalizado (PT-BR) | Orientação Léxica | Peso Base no Dicionário | Ocorrências no Corpus | % das Menções Léxicas |",
            "| :--- | :--- | ---: | ---: | ---: |",
        ]
    )

    for lx in lex_rows[:15]:
        lines.append(
            f"| `{lx['lexicon_term']}` | `{lx['polarity_orientation']}` | "
            f"`{lx['base_lexicon_weight']:+.1f}` | **{lx['occurrences_count']:,}** | "
            f"`{lx['share_of_mentions_pct']:.2f}%` |"
        )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    exported["executive_markdown_report"] = str(report_path)
    return exported
