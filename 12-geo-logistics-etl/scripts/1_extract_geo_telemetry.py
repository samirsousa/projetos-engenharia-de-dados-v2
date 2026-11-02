"""
Etapa 1 (Extract): Geração e Extração de Telemetria GPS e Manifesto de Cargas Brutas.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RAW_TELEMETRY_DIR, ensure_directories
from src.geo_extractor import GeospatialLogisticsExtractor, save_raw_telemetry_csvs


def main() -> None:
    ensure_directories()
    extractor = GeospatialLogisticsExtractor(seed=42)
    batches = extractor.generate_raw_batches(total_shipments=960)
    paths = save_raw_telemetry_csvs(batches, output_dir=RAW_TELEMETRY_DIR)

    print("=" * 80)
    print("[STAGE 1 - EXTRACT] TELEMETRIA GEOESPACIAL & REMESSAS BRUTAS EXTRAÍDAS")
    print("=" * 80)
    for name, path in paths.items():
        print(f"  -> {name:<18}: {len(batches[name]):>5,} registros | {path}")


if __name__ == "__main__":
    main()
