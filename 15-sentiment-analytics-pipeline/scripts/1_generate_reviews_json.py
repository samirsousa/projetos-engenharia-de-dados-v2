"""
Etapa 1: Geração do Arquivo JSON de Avaliações de Clientes e Menções Sociais (`customer_social_reviews.json`).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.review_generator import save_reviews_json


def main() -> None:
    meta = save_reviews_json(total_reviews=1250, seed=42)
    print("=" * 80)
    print("[ETAPA 1] ARQUIVO JSON DE AVALIAÇÕES E REDES SOCIAIS GERADO")
    print("=" * 80)
    print(f"  -> Arquivo JSON : {meta['json_path']}")
    print(f"  -> Total Reviews: {meta['total_reviews']:,}")


if __name__ == "__main__":
    main()
