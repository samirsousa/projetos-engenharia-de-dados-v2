"""
Etapa 3 (Load): Carga no Banco Relacional SQLite, Exportação GeoJSON/Parquet e Relatório Executivo.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import MAP_EXPORTS_DIR, SQLITE_DB_PATH, ensure_directories
from src.geo_extractor import GeospatialLogisticsExtractor, save_raw_telemetry_csvs
from src.geo_loader import (
    export_map_layers_and_geojson,
    generate_geospatial_executive_report,
    load_to_sqlite_warehouse,
)
from src.geo_transformer import GeospatialLogisticsTransformer


def main() -> None:
    ensure_directories()
    extractor = GeospatialLogisticsExtractor(seed=42)
    batches = extractor.generate_raw_batches(total_shipments=960)
    save_raw_telemetry_csvs(batches)

    transformer = GeospatialLogisticsTransformer()
    transformed = transformer.transform(batches["raw_hubs"], batches["raw_shipments"])

    counts = load_to_sqlite_warehouse(transformed, db_path=SQLITE_DB_PATH)
    exported = export_map_layers_and_geojson(transformed, db_path=SQLITE_DB_PATH)
    report_path, kpis = generate_geospatial_executive_report(transformed)

    print("=" * 80)
    print("[STAGE 3 - LOAD] WAREHOUSE GEOESPACIAL & EXPORTAÇÃO DE MAPAS GERENCIAIS")
    print("=" * 80)
    for tbl, cnt in counts.items():
        print(f"  -> Tabela SQL '{tbl:<30}': {cnt:>5,} linhas")
    print(f"  -> GeoJSON RFC 7946 exportado em: {exported['geojson_map']}")
    print(f"  -> Relatório Executivo gerado em: {report_path}")


if __name__ == "__main__":
    main()
