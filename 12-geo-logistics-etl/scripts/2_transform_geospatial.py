"""
Etapa 2 (Transform): Cálculo de Distância Haversine/Rodoviária, Geohash, Densidade Regional e Gargalos.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.geo_extractor import GeospatialLogisticsExtractor
from src.geo_transformer import GeospatialLogisticsTransformer


def main() -> None:
    extractor = GeospatialLogisticsExtractor(seed=42)
    batches = extractor.generate_raw_batches(total_shipments=960)
    transformer = GeospatialLogisticsTransformer()
    transformed = transformer.transform(batches["raw_hubs"], batches["raw_shipments"])

    print("=" * 80)
    print("[STAGE 2 - TRANSFORM] CÁLCULOS GEODÉSICOS, DENSIDADE & GARGALOS LOGÍSTICOS")
    print("=" * 80)
    for key, rows in transformed.items():
        print(f"  -> {key:<34}: {len(rows):>5,} registros processados")


if __name__ == "__main__":
    main()
