"""
Script 3: Carregador Histórico de Indicadores Macroeconômicos em SQLite.
Ponto de entrada CLI para execução isolada da etapa de Carga (Data Warehouse).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.loader import MacroWarehouseLoader


def main() -> None:
    loader = MacroWarehouseLoader()
    loader.run_load()


if __name__ == "__main__":
    main()
