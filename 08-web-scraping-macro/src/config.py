"""Configurações centralizadas, políticas de Web Scraping ético e logging do projeto."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ScrapingPipelineConfig:
    """Configuração imutável dos diretórios, políticas de rede e banco de dados."""

    base_dir: Path = PROJECT_ROOT
    data_dir: Path = field(init=False)
    html_portal_dir: Path = field(init=False)
    bronze_raw_dir: Path = field(init=False)
    silver_staged_dir: Path = field(init=False)
    warehouse_dir: Path = field(init=False)
    sqlite_db_path: Path = field(init=False)
    logs_dir: Path = field(init=False)
    reports_dir: Path = field(init=False)

    # Parâmetros de Web Scraping Ético e Resiliência
    user_agent: str = (
        "MacroDataEngineeringBot/1.0 (+https://example.org/data-governance; "
        "contact=data-eng@example.org; Python-urllib/3.13)"
    )
    request_timeout_sec: float = 8.0
    rate_limit_delay_sec: float = 0.05
    max_retries: int = 3
    backoff_base_sec: float = 0.1
    backoff_Max_sec: float = 2.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_dir", self.base_dir / "data")
        object.__setattr__(self, "html_portal_dir", self.base_dir / "data" / "mock_portal_html")
        object.__setattr__(self, "bronze_raw_dir", self.base_dir / "data" / "bronze_raw")
        object.__setattr__(self, "silver_staged_dir", self.base_dir / "data" / "silver_staged")
        object.__setattr__(self, "warehouse_dir", self.base_dir / "data" / "warehouse")
        object.__setattr__(
            self, "sqlite_db_path", self.base_dir / "data" / "warehouse" / "macro_indicators.db"
        )
        object.__setattr__(self, "logs_dir", self.base_dir / "logs")
        object.__setattr__(self, "reports_dir", self.base_dir / "reports")

    def ensure_directories(self) -> None:
        """Cria toda a hierarquia de diretórios necessária para o pipeline."""
        for path in (
            self.html_portal_dir,
            self.bronze_raw_dir,
            self.silver_staged_dir,
            self.warehouse_dir,
            self.logs_dir,
            self.reports_dir,
        ):
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
