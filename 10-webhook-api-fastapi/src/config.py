"""Configurações centralizadas e logging do Webhook & API Gateway de Logs Operacionais."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class APIGatewayConfig:
    """Configuração imutável do Webhook Receiver e API Gateway de Logs."""

    base_dir: Path = PROJECT_ROOT
    data_dir: Path = field(init=False)
    sqlite_db_path: Path = field(init=False)
    reports_dir: Path = field(init=False)

    api_title: str = "Operational Logs Webhook & API Gateway"
    api_version: str = "1.0.0"
    webhook_secret_key: str = field(
        default_factory=lambda: os.environ.get("WEBHOOK_SECRET_KEY", "whsec_prod_operational_gateway_2026")
    )
    require_hmac_signature: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_dir", self.base_dir / "data")
        object.__setattr__(
            self, "sqlite_db_path", self.base_dir / "data" / "operational_logs_gateway.db"
        )
        object.__setattr__(self, "reports_dir", self.base_dir / "reports")

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.reports_dir):
            path.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Configura logger estruturado com timestamps ISO-8601."""
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
