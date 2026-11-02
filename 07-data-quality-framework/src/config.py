"""Configurações de diretórios e logging estruturado para o Data Quality Framework."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_DIR = PROJECT_ROOT


@dataclass(frozen=True)
class DQConfig:
    """Estrutura imutável de caminhos para artefatos de Data Quality & Observability."""

    base_dir: Path = DEFAULT_BASE_DIR
    data_dir: Path = field(init=False)
    samples_dir: Path = field(init=False)
    contracts_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)
    anomalies_dir: Path = field(init=False)
    alerts_dir: Path = field(init=False)
    reports_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_dir", self.base_dir / "data")
        object.__setattr__(self, "samples_dir", self.base_dir / "data" / "samples")
        object.__setattr__(self, "contracts_dir", self.base_dir / "data" / "contracts")
        object.__setattr__(self, "logs_dir", self.base_dir / "logs")
        object.__setattr__(self, "anomalies_dir", self.base_dir / "logs" / "anomalies")
        object.__setattr__(self, "alerts_dir", self.base_dir / "logs" / "alerts")
        object.__setattr__(self, "reports_dir", self.base_dir / "reports")

    def ensure_directories(self) -> None:
        """Garante a existência de todos os diretórios operacionais do framework."""
        for directory in (
            self.samples_dir,
            self.contracts_dir,
            self.anomalies_dir,
            self.alerts_dir,
            self.reports_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Inicializa logger estruturado com timestamp ISO para observabilidade."""
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
