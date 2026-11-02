"""Configurações centralizadas e utilitários de infraestrutura para o pipeline CDC."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


@dataclass(frozen=True)
class PipelineConfig:
    """Configuração imutável dos diretórios e bancos de dados do pipeline CDC."""

    data_dir: Path = DEFAULT_DATA_DIR
    oltp_db_path: Path = field(init=False)
    silver_db_path: Path = field(init=False)
    cdc_logs_dir: Path = field(init=False)
    cdc_archive_dir: Path = field(init=False)
    checkpoints_dir: Path = field(init=False)
    connector_offset_path: Path = field(init=False)
    reports_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "oltp_db_path", self.data_dir / "oltp" / "oltp_source.db")
        object.__setattr__(self, "silver_db_path", self.data_dir / "silver" / "warehouse_silver.db")
        object.__setattr__(self, "cdc_logs_dir", self.data_dir / "bronze_cdc_logs")
        object.__setattr__(self, "cdc_archive_dir", self.data_dir / "bronze_cdc_logs" / "archive")
        object.__setattr__(self, "checkpoints_dir", self.data_dir / "checkpoints")
        object.__setattr__(
            self,
            "connector_offset_path",
            self.data_dir / "checkpoints" / "debezium_sim_offset.json",
        )
        object.__setattr__(self, "reports_dir", self.data_dir / "reports")

    def ensure_directories(self) -> None:
        """Garante que toda a árvore de diretórios do pipeline exista."""
        for path in (
            self.oltp_db_path.parent,
            self.silver_db_path.parent,
            self.cdc_logs_dir,
            self.cdc_archive_dir,
            self.checkpoints_dir,
            self.reports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Configura logger padronizado para observabilidade de engenharia de dados."""
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
