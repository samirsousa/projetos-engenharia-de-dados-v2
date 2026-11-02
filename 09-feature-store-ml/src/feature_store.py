"""
Camada Gold: Local Feature Store (Offline Parquet/CSV + Online Low-Latency Store + Feature Registry).

Inspirado na arquitetura do Feast / Tecton:
- `materialize_gold_layer()`: Persiste vetores de features no Offline Store (Parquet colunar,
  matriz Z-Score normalizada e CSV) e no Online Store (SQLite indexado Key-Value + Relacional).
- `get_historical_features()`: API de recuperação em lote para treinamento de modelos ML.
- `get_online_features()`: API de baixa latência (< 1ms) para inferência em tempo real.
- `generate_feature_store_report()`: Calcula correlações de Pearson com o target de Churn/CLV
  e estatísticas por segmento RFM.
"""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.config import FeatureStoreConfig, setup_logger
from src.feature_engineering import CustomerFeatureVector

logger = setup_logger("Gold-Feature-Store")


NUMERIC_FEATURE_COLUMNS = [
    "tenure_days",
    "rfm_recency_days",
    "rfm_frequency_total",
    "rfm_frequency_30d",
    "rfm_frequency_90d",
    "rfm_monetary_total",
    "rfm_monetary_30d",
    "rfm_monetary_90d",
    "rfm_r_score",
    "rfm_f_score",
    "rfm_m_score",
    "rfm_composite_score",
    "aov_lifetime",
    "rolling_aov_last_3",
    "rolling_aov_30d",
    "rolling_aov_90d",
    "aov_momentum_ratio",
    "ticket_stddev",
    "ticket_cv",
    "avg_items_per_order",
    "weekend_purchase_ratio",
    "night_purchase_ratio",
    "peak_hour_sin",
    "peak_hour_cos",
    "avg_interpurchase_days",
    "stddev_interpurchase_days",
    "overdue_cadence_ratio",
    "category_shannon_entropy",
    "distinct_categories_count",
    "discount_usage_rate",
    "avg_discount_depth_pct",
    "pix_payment_share",
    "cancellation_rate",
]


ONLINE_STORE_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS online_kv_feature_store (
    customer_id         TEXT PRIMARY KEY,
    as_of_timestamp     TEXT NOT NULL,
    rfm_segment         TEXT NOT NULL,
    feature_vector_json TEXT NOT NULL,
    materialized_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gold_customer_features_table (
    customer_id                 TEXT PRIMARY KEY,
    as_of_timestamp             TEXT NOT NULL,
    state_uf                    TEXT NOT NULL,
    acquisition_channel         TEXT NOT NULL,
    tenure_days                 INTEGER NOT NULL,
    rfm_recency_days            REAL NOT NULL,
    rfm_frequency_total         INTEGER NOT NULL,
    rfm_frequency_30d           INTEGER NOT NULL,
    rfm_frequency_90d           INTEGER NOT NULL,
    rfm_monetary_total          REAL NOT NULL,
    rfm_monetary_30d            REAL NOT NULL,
    rfm_monetary_90d            REAL NOT NULL,
    rfm_r_score                 INTEGER NOT NULL,
    rfm_f_score                 INTEGER NOT NULL,
    rfm_m_score                 INTEGER NOT NULL,
    rfm_composite_score         REAL NOT NULL,
    rfm_segment                 TEXT NOT NULL,
    aov_lifetime                REAL NOT NULL,
    rolling_aov_last_3          REAL NOT NULL,
    rolling_aov_30d             REAL NOT NULL,
    rolling_aov_90d             REAL NOT NULL,
    aov_momentum_ratio          REAL NOT NULL,
    ticket_stddev               REAL NOT NULL,
    ticket_cv                   REAL NOT NULL,
    avg_items_per_order         REAL NOT NULL,
    weekend_purchase_ratio      REAL NOT NULL,
    night_purchase_ratio        REAL NOT NULL,
    peak_hour_sin               REAL NOT NULL,
    peak_hour_cos               REAL NOT NULL,
    dominant_quarter            TEXT NOT NULL,
    avg_interpurchase_days      REAL NOT NULL,
    stddev_interpurchase_days   REAL NOT NULL,
    overdue_cadence_ratio       REAL NOT NULL,
    category_shannon_entropy    REAL NOT NULL,
    distinct_categories_count   INTEGER NOT NULL,
    discount_usage_rate         REAL NOT NULL,
    avg_discount_depth_pct      REAL NOT NULL,
    pix_payment_share           REAL NOT NULL,
    cancellation_rate           REAL NOT NULL,
    target_churn_30d            INTEGER NOT NULL,
    target_next_30d_spend       REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gold_rfm_segment ON gold_customer_features_table(rfm_segment);
CREATE INDEX IF NOT EXISTS idx_gold_churn_target ON gold_customer_features_table(target_churn_30d);
"""


class LocalFeatureStore:
    """Gerenciador da Feature Store Local (Offline Parquet/CSV + Online SQLite + Registry)."""

    def __init__(self, config: Optional[FeatureStoreConfig] = None) -> None:
        self.config = config or FeatureStoreConfig()
        self.config.ensure_directories()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    @staticmethod
    def _write_parquet_or_fallback(records: List[Dict[str, Any]], path: Path) -> str:
        try:
            import pyarrow as pa  # type: ignore
            import pyarrow.parquet as pq  # type: ignore

            table = pa.Table.from_pylist(records)
            pq.write_table(table, path, compression="snappy")
            return "pyarrow-snappy"
        except Exception:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"columns": list(records[0].keys()), "rows": records}, fh, indent=2)
            return "pure-python-json-fallback"

    @staticmethod
    def _compute_scaler_stats(
        records: List[Dict[str, Any]], feature_cols: Sequence[str]
    ) -> Dict[str, Dict[str, float]]:
        """Calcula média (mean) e desvio padrão (std) de cada feature numérica para Z-Score Scaling."""
        stats: Dict[str, Dict[str, float]] = {}
        n = len(records)
        for col in feature_cols:
            vals = [float(r[col]) for r in records]
            mean_val = sum(vals) / n if n > 0 else 0.0
            variance = sum((v - mean_val) ** 2 for v in vals) / n if n > 1 else 0.0
            std_val = math.sqrt(variance)
            stats[col] = {
                "mean": round(mean_val, 6),
                "std": round(std_val if std_val > 1e-9 else 1.0, 6),
                "min": round(min(vals), 4) if vals else 0.0,
                "max": round(max(vals), 4) if vals else 0.0,
            }
        return stats

    @staticmethod
    def _pearson_correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
        """Calcula o coeficiente de correlação linear de Pearson r(X, Y) em Python puro."""
        n = len(xs)
        if n < 2 or len(ys) != n:
            return 0.0
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
        den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
        if den_x < 1e-12 or den_y < 1e-12:
            return 0.0
        return round(num / (den_x * den_y), 4)

    def materialize_gold_layer(
        self, vectors: List[CustomerFeatureVector]
    ) -> Dict[str, Any]:
        """
        Materializa os vetores de features na Camada Gold:
        1. Offline Store: `gold_customer_features.parquet`, `gold_customer_features_scaled.parquet` e `.csv`.
        2. Online Store: Banco SQLite `online_feature_store.db` (Key-Value + Tabela Tipada).
        3. Feature Registry: `feature_registry.json` com estatísticas de normalização Z-Score.
        """
        if not vectors:
            raise ValueError("Lista de vetores de features vazia para materialização.")

        raw_dicts = [asdict(v) for v in vectors]
        now_iso = self._utc_now_iso()

        # 1. Calcula parâmetros de padronização Z-Score para algoritmos baseados em gradiente/distância
        scaler_stats = self._compute_scaler_stats(raw_dicts, NUMERIC_FEATURE_COLUMNS)
        scaled_dicts: List[Dict[str, Any]] = []
        for row in raw_dicts:
            scaled_row: Dict[str, Any] = {
                "customer_id": row["customer_id"],
                "as_of_timestamp": row["as_of_timestamp"],
                "rfm_segment": row["rfm_segment"],
            }
            for col in NUMERIC_FEATURE_COLUMNS:
                mean_c = scaler_stats[col]["mean"]
                std_c = scaler_stats[col]["std"]
                scaled_row[f"{col}_zscore"] = round((float(row[col]) - mean_c) / std_c, 6)
            scaled_row["target_churn_30d"] = row["target_churn_30d"]
            scaled_row["target_next_30d_spend"] = row["target_next_30d_spend"]
            scaled_dicts.append(scaled_row)

        # 2. Persiste Offline Store (Parquet Bruto, Parquet Z-Score Scaled e CSV)
        engine_used = self._write_parquet_or_fallback(raw_dicts, self.config.offline_parquet_path)
        self._write_parquet_or_fallback(scaled_dicts, self.config.offline_scaled_parquet_path)

        fieldnames = list(raw_dicts[0].keys())
        with open(self.config.offline_csv_path, "w", encoding="utf-8", newline="") as csv_fh:
            writer = csv.DictWriter(csv_fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(raw_dicts)

        # 3. Persiste Online Store (SQLite Key-Value + Tabela Colunar)
        if self.config.online_db_path.exists():
            self.config.online_db_path.unlink()

        conn = sqlite3.connect(str(self.config.online_db_path))
        try:
            conn.executescript(ONLINE_STORE_DDL)
            kv_rows = [
                (
                    str(r["customer_id"]),
                    str(r["as_of_timestamp"]),
                    str(r["rfm_segment"]),
                    json.dumps(r, ensure_ascii=False),
                    now_iso,
                )
                for r in raw_dicts
            ]
            conn.executemany(
                "INSERT INTO online_kv_feature_store VALUES (?, ?, ?, ?, ?)",
                kv_rows,
            )

            placeholders = ", ".join(["?"] * len(fieldnames))
            tuple_rows = [tuple(r[col] for col in fieldnames) for r in raw_dicts]
            conn.executemany(
                f"INSERT INTO gold_customer_features_table VALUES ({placeholders})",
                tuple_rows,
            )
            conn.commit()
        finally:
            conn.close()

        # 4. Persiste Catálogo de Metadados (Feature Registry)
        registry_doc = {
            "feature_store_name": "ecommerce_ml_gold_feature_store",
            "version": "1.0.0",
            "entity_key": "customer_id",
            "point_in_time_column": "as_of_timestamp",
            "materialized_at_utc": now_iso,
            "total_entities": len(raw_dicts),
            "total_features": len(fieldnames) - 2,
            "storage_layers": {
                "offline_parquet": str(self.config.offline_parquet_path),
                "offline_scaled_parquet": str(self.config.offline_scaled_parquet_path),
                "offline_csv": str(self.config.offline_csv_path),
                "online_sqlite_store": str(self.config.online_db_path),
                "parquet_engine": engine_used,
            },
            "feature_views": {
                "rfm_view": [c for c in fieldnames if c.startswith("rfm_")],
                "rolling_ticket_view": [
                    "aov_lifetime",
                    "rolling_aov_last_3",
                    "rolling_aov_30d",
                    "rolling_aov_90d",
                    "aov_momentum_ratio",
                    "ticket_stddev",
                    "ticket_cv",
                    "avg_items_per_order",
                ],
                "seasonality_and_cadence_view": [
                    "weekend_purchase_ratio",
                    "night_purchase_ratio",
                    "peak_hour_sin",
                    "peak_hour_cos",
                    "dominant_quarter",
                    "avg_interpurchase_days",
                    "stddev_interpurchase_days",
                    "overdue_cadence_ratio",
                    "category_shannon_entropy",
                    "distinct_categories_count",
                    "discount_usage_rate",
                    "avg_discount_depth_pct",
                    "pix_payment_share",
                    "cancellation_rate",
                ],
                "supervised_targets_view": ["target_churn_30d", "target_next_30d_spend"],
            },
            "zscore_scaler_parameters": scaler_stats,
        }

        with open(self.config.registry_json_path, "w", encoding="utf-8") as fh:
            json.dump(registry_doc, fh, indent=2, ensure_ascii=False)

        logger.info(
            "Camada Gold materializada | entidades=%d | Offline Parquet=%s | Online DB=%s",
            len(raw_dicts),
            self.config.offline_parquet_path.name,
            self.config.online_db_path.name,
        )
        return registry_doc

    def get_online_features(
        self,
        customer_ids: Sequence[str],
        feature_names: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        API de Baixa Latência (Online Feature Store) para inferência de modelos em tempo real.
        Busca os vetores materializados na tabela indexada `online_kv_feature_store`.
        """
        if not customer_ids:
            return []

        placeholders = ", ".join(["?"] * len(customer_ids))
        conn = sqlite3.connect(str(self.config.online_db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"SELECT customer_id, feature_vector_json FROM online_kv_feature_store WHERE customer_id IN ({placeholders})",
                tuple(customer_ids),
            ).fetchall()
        finally:
            conn.close()

        by_id = {str(r["customer_id"]): json.loads(r["feature_vector_json"]) for r in rows}
        results: List[Dict[str, Any]] = []
        for cid in customer_ids:
            vec = by_id.get(cid)
            if not vec:
                continue
            if feature_names:
                filtered = {"customer_id": cid}
                for fname in feature_names:
                    if fname in vec:
                        filtered[fname] = vec[fname]
                results.append(filtered)
            else:
                results.append(vec)
        return results

    def get_historical_training_dataset(
        self, scaled: bool = False
    ) -> List[Dict[str, Any]]:
        """
        API Offline Feature Store para recuperação do dataset completo de treinamento ML
        diretamente da Camada Gold em formato Parquet.
        """
        target_path = (
            self.config.offline_scaled_parquet_path if scaled else self.config.offline_parquet_path
        )
        try:
            import pyarrow.parquet as pq  # type: ignore

            return pq.read_table(target_path).to_pylist()
        except Exception:
            with open(target_path, "r", encoding="utf-8") as fh:
                return list(json.load(fh)["rows"])

    def generate_feature_store_report(self) -> Path:
        """Gera relatório técnico de perfilamento das features, correlações com Churn e latência Online."""
        report_path = self.config.reports_dir / "feature_store_ml_report.md"

        conn = sqlite3.connect(str(self.config.online_db_path))
        conn.row_factory = sqlite3.Row
        try:
            all_rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM gold_customer_features_table ORDER BY customer_id ASC"
                ).fetchall()
            ]
            segment_summary = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT
                        rfm_segment,
                        COUNT(*) AS customer_count,
                        ROUND(AVG(rfm_recency_days), 1) AS avg_recency_days,
                        ROUND(AVG(rfm_frequency_total), 1) AS avg_frequency,
                        ROUND(AVG(rfm_monetary_total), 2) AS avg_ltv_brl,
                        ROUND(AVG(rolling_aov_last_3), 2) AS avg_rolling_aov_3,
                        ROUND(AVG(aov_momentum_ratio), 3) AS avg_momentum,
                        ROUND(AVG(target_churn_30d) * 100.0, 1) AS churn_rate_pct
                      FROM gold_customer_features_table
                     GROUP BY rfm_segment
                     ORDER BY avg_ltv_brl DESC
                    """
                ).fetchall()
            ]
        finally:
            conn.close()

        # Benchmark de latência do Online Store (consulta de 5 clientes em tempo real)
        t0 = time.perf_counter_ns()
        _ = self.get_online_features(
            ["CUST-0001", "CUST-0002", "CUST-0003", "CUST-0004", "CUST-0005"],
            feature_names=[
                "rfm_recency_days",
                "rfm_composite_score",
                "rolling_aov_last_3",
                "aov_momentum_ratio",
                "overdue_cadence_ratio",
            ],
        )
        online_latency_ms = round((time.perf_counter_ns() - t0) / 1_000_000.0, 3)

        # Calcula correlação de Pearson de cada feature numérica contra `target_churn_30d`
        churn_targets = [float(r["target_churn_30d"]) for r in all_rows]
        spend_targets = [float(r["target_next_30d_spend"]) for r in all_rows]

        correlations: List[Dict[str, Any]] = []
        for col in NUMERIC_FEATURE_COLUMNS:
            col_vals = [float(r[col]) for r in all_rows]
            r_churn = self._pearson_correlation(col_vals, churn_targets)
            r_spend = self._pearson_correlation(col_vals, spend_targets)
            correlations.append(
                {
                    "feature": col,
                    "corr_churn_30d": r_churn,
                    "abs_corr_churn": abs(r_churn),
                    "corr_next_30d_spend": r_spend,
                }
            )
        correlations.sort(key=lambda item: item["abs_corr_churn"], reverse=True)

        lines = [
            "# Relatório Analítico da Feature Store — Camada Gold para Machine Learning",
            "",
            f"- **Gerado em (UTC):** `{self._utc_now_iso()}`",
            f"- **Point-in-Time Cutoff (`as_of_timestamp`):** `{self.config.default_as_of_date}`",
            f"- **Total de Clientes Materializados:** `{len(all_rows)}`",
            f"- **Latência de Inferência Online (5 entidades):** `{online_latency_ms} ms`",
            "",
            "---",
            "",
            "## 1. Perfil Comportamental por Segmento RFM e Taxa Real de Churn (Holdout 30d)",
            "",
            "| Segmento RFM | Clientes | Recência Média (d) | Frequência Média | LTV Médio (R$) | Ticket Móvel (MA3) | Momentum Ticket | Taxa de Churn 30d (%) |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for seg in segment_summary:
            lines.append(
                f"| `{seg['rfm_segment']}` | {seg['customer_count']} | `{seg['avg_recency_days']}` | "
                f"`{seg['avg_frequency']}` | R$ {float(seg['avg_ltv_brl']):,.2f} | "
                f"R$ {float(seg['avg_rolling_aov_3']):,.2f} | `{seg['avg_momentum']}` | "
                f"**{seg['churn_rate_pct']}%** |"
            )

        lines.extend(
            [
                "",
                "---",
                "",
                "## 2. Importância Preditiva Linear — Top 12 Features vs `target_churn_30d` e `target_next_30d_spend`",
                "",
                "| Ranking | Feature Analítica | Correlação Pearson com Churn 30d ($r$) | Correlação com Gasto Futuro 30d ($r$) | Interpretação Preditiva |",
                "| :---: | :--- | :---: | :---: | :--- |",
            ]
        )

        for idx, item in enumerate(correlations[:12], start=1):
            r_c = item["corr_churn_30d"]
            direction = (
                "Fator de Risco de Churn (+)" if r_c > 0 else "Fator de Retenção / Engajamento (-)"
            )
            lines.append(
                f"| {idx} | `{item['feature']}` | `{r_c:+.4f}` | `{item['corr_next_30d_spend']:+.4f}` | {direction} |"
            )

        lines.append("")
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path
