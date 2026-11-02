"""Configurações centralizadas de caminhos e observabilidade para a Feature Store ML."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class FeatureStoreConfig:
    """Configuração imutável dos diretórios e stores da plataforma de Features."""

    base_dir: Path = PROJECT_ROOT
    data_dir: Path = field(init=False)
    bronze_oltp_dir: Path = field(init=False)
    oltp_db_path: Path = field(init=False)
    gold_store_dir: Path = field(init=False)
    offline_parquet_path: Path = field(init=False)
    offline_scaled_parquet_path: Path = field(init=False)
    offline_csv_path: Path = field(init=False)
    online_db_path: Path = field(init=False)
    registry_json_path: Path = field(init=False)
    reports_dir: Path = field(init=False)

    # Timestamp de referência padrão (Point-in-Time Cutoff para evitar Data Leakage)
    default_as_of_date: str = "2026-10-01T23:59:59Z"
    default_label_horizon_days: int = 30

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_dir", self.base_dir / "data")
        object.__setattr__(self, "bronze_oltp_dir", self.base_dir / "data" / "bronze_oltp")
        object.__setattr__(
            self, "oltp_db_path", self.base_dir / "data" / "bronze_oltp" / "ecommerce_oltp.db"
        )
        object.__setattr__(
            self, "gold_store_dir", self.base_dir / "data" / "gold_feature_store"
        )
        object.__setattr__(
            self,
            "offline_parquet_path",
            self.base_dir / "data" / "gold_feature_store" / "gold_customer_features.parquet",
        )
        object.__setattr__(
            self,
            "offline_scaled_parquet_path",
            self.base_dir / "data" / "gold_feature_store" / "gold_customer_features_scaled.parquet",
        )
        object.__setattr__(
            self,
            "offline_csv_path",
            self.base_dir / "data" / "gold_feature_store" / "gold_customer_features.csv",
        )
        object.__setattr__(
            self,
            "online_db_path",
            self.base_dir / "data" / "gold_feature_store" / "online_feature_store.db",
        )
        object.__setattr__(
            self,
            "registry_json_path",
            self.base_dir / "data" / "gold_feature_store" / "feature_registry.json",
        )
        object.__setattr__(self, "reports_dir", self.base_dir / "reports")

    def ensure_directories(self) -> None:
        """Cria toda a estrutura de diretórios da Feature Store."""
        for path in (
            self.bronze_oltp_dir,
            self.gold_store_dir,
            self.reports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Inicializa logger estruturado com timestamps ISO-8601."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
