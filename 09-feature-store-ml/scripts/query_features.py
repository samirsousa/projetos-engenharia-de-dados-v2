"""
CLI de Consulta à Feature Store (Online Serving & Offline Batch Retrieval).

Permite consultar o vetor de features de um ou mais clientes em tempo real
a partir do Online Store (`online_feature_store.db`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.feature_store import LocalFeatureStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consulta vetores de features na Online Feature Store.")
    parser.add_argument(
        "--customer-ids",
        nargs="+",
        default=["CUST-0001", "CUST-0003", "CUST-0004"],
        help="Lista de IDs de clientes para consulta online (ex: CUST-0001 CUST-0002).",
    )
    parser.add_argument(
        "--features",
        nargs="*",
        default=None,
        help="Subconjunto opcional de features a retornar (padrão: todas).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = LocalFeatureStore()
    results = store.get_online_features(
        customer_ids=args.customer_ids,
        feature_names=args.features,
    )
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
