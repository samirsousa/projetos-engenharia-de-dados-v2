"""
Script 1: Extrator Robusto de Web Scraping Ético (HTML DOM + Retry Logic).
Ponto de entrada CLI para execução isolada da etapa de Extração (Camada Bronze).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extractor import MacroWebExtractor


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrator Web Scraping de Indicadores Macroeconômicos.")
    parser.add_argument(
        "--simulate-failures",
        type=int,
        default=1,
        help="Quantidade de falhas transitórias HTTP 503 a simular para demonstrar Retry/Backoff (padrão: 1).",
    )
    args = parser.parse_args()

    extractor = MacroWebExtractor(simulate_transient_failures=args.simulate_failures)
    extractor.run_extraction()


if __name__ == "__main__":
    main()
