"""
Script 2: Transformador de Dados Macroeconômicos (Limpeza, Normalização e Schema Tipado).
Ponto de entrada CLI para execução isolada da etapa de Transformação (Camada Silver).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.transformer import MacroDataTransformer


def main() -> None:
    transformer = MacroDataTransformer()
    transformer.run_transformation()


if __name__ == "__main__":
    main()
