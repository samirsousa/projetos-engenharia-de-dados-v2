"""
Orquestrador End-to-End da Feature Store para Machine Learning (Camada Gold).

Executa o fluxo completo:
1. Geração da base transacional OLTP de e-commerce (`ecommerce_oltp.db`).
2. Cálculo Point-in-Time das 37 features analíticas e targets supervisionados por cliente.
3. Materialização na Camada Gold:
   - Offline Store: `gold_customer_features.parquet`, `gold_customer_features_scaled.parquet` e `.csv`
   - Online Store: `online_feature_store.db` (Key-Value + Tabela SQL indexada)
   - Catálogo: `feature_registry.json`
4. Geração do Relatório de Perfilamento e Importância Preditiva (`feature_store_ml_report.md`).
"""

from __future__ import annotations

import argparse
import shutil

from src.config import FeatureStoreConfig, setup_logger
from src.feature_engineering import FeatureEngineeringPipeline
from src.feature_store import LocalFeatureStore
from src.oltp_seeder import EcommerceOLTPSeeder

logger = setup_logger("FeatureStore-Orchestrator")


def run_feature_store_pipeline(clean_start: bool = False, num_customers: int = 60, seed: int = 42) -> None:
    config = FeatureStoreConfig()

    if clean_start:
        for folder in (config.data_dir, config.reports_dir):
            if folder.exists():
                shutil.rmtree(folder)

    config.ensure_directories()

    logger.info("=" * 88)
    logger.info("INICIANDO PIPELINE DE FEATURE STORE PARA MACHINE LEARNING (ARQUITETURA MEDALLION)")
    logger.info("=" * 88)

    # 1. Popula base transacional OLTP (Camada Bronze)
    seeder = EcommerceOLTPSeeder(config=config, seed=seed)
    oltp_stats = seeder.seed_database(num_customers=num_customers)

    # 2. Computa features analíticas com garantia Point-in-Time
    fe_pipeline = FeatureEngineeringPipeline(config=config)
    feature_vectors = fe_pipeline.compute_customer_features()

    # 3. Materializa na Camada Gold (Offline Parquet/CSV + Online Store + Feature Registry)
    store = LocalFeatureStore(config=config)
    registry = store.materialize_gold_layer(feature_vectors)
    report_path = store.generate_feature_store_report()

    # 4. Demonstração de consulta Online de baixa latência para inferência em tempo real
    sample_online = store.get_online_features(
        customer_ids=["CUST-0001", "CUST-0004"],
        feature_names=[
            "rfm_segment",
            "rfm_recency_days",
            "rfm_frequency_total",
            "rfm_monetary_total",
            "rolling_aov_last_3",
            "aov_momentum_ratio",
            "weekend_purchase_ratio",
            "overdue_cadence_ratio",
            "target_churn_30d",
        ],
    )

    logger.info("-" * 88)
    logger.info("AMOSTRA DE CONSULTA ONLINE (REAL-TIME MODEL SERVING API):")
    for vec in sample_online:
        logger.info("  Entidade %s -> %s", vec["customer_id"], vec)

    logger.info("=" * 88)
    logger.info("RESUMO EXECUTIVO DA FEATURE STORE (CAMADA GOLD)")
    logger.info("  Transações OLTP Processadas : %d pedidos de %d clientes", oltp_stats["orders"], oltp_stats["customers"])
    logger.info("  Point-in-Time Cutoff        : %s", config.default_as_of_date)
    logger.info("  Features por Entidade       : %d features + 2 targets supervisionados", registry["total_features"])
    logger.info("  Offline Parquet (Bruto)     : %s", config.offline_parquet_path)
    logger.info("  Offline Parquet (Z-Score)   : %s", config.offline_scaled_parquet_path)
    logger.info("  Offline CSV                 : %s", config.offline_csv_path)
    logger.info("  Online Store (SQLite KV)    : %s", config.online_db_path)
    logger.info("  Feature Registry JSON       : %s", config.registry_json_path)
    logger.info("  Relatório Analítico ML      : %s", report_path)
    logger.info("=" * 88)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa o pipeline completo da Feature Store para Machine Learning."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove data/ e reports/ antes de iniciar uma nova materialização.",
    )
    parser.add_argument(
        "--customers",
        type=int,
        default=60,
        help="Número de clientes a simular na base de e-commerce (padrão: 60).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed para reprodutibilidade determinística (padrão: 42).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_feature_store_pipeline(
        clean_start=args.clean,
        num_customers=args.customers,
        seed=args.seed,
    )
