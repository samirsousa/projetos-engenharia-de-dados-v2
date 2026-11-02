"""
Etapa 2: Processamento de Limpeza de Texto e Dicionário de Polaridade PT-BR (NLP Rules / Lexicon).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RAW_REVIEWS_JSON_PATH
from src.sentiment_engine import SentimentAnalyticsProcessor


def main() -> None:
    processor = SentimentAnalyticsProcessor()
    enriched = processor.process_json_file(RAW_REVIEWS_JSON_PATH)

    pos = sum(1 for r in enriched if r["sentiment_label"] == "POSITIVE")
    neu = sum(1 for r in enriched if r["sentiment_label"] == "NEUTRAL")
    neg = sum(1 for r in enriched if r["sentiment_label"] == "NEGATIVE")

    print("=" * 80)
    print("[ETAPA 2] LIMPEZA DE TEXTO E ANÁLISE DE SENTIMENTO (LÉXICO PT-BR) CONCLUÍDAS")
    print("=" * 80)
    print(f"  -> Total de avaliações processadas: {len(enriched):,}")
    print(f"  -> Positivas: {pos:,} | Neutras: {neu:,} | Negativas: {neg:,}")


if __name__ == "__main__":
    main()
