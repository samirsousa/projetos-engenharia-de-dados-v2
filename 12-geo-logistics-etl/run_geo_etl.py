"""
Orquestrador End-to-End do Projeto 12: ETL de Dados Geoespaciais e Logísticos.

Executa o pipeline completo:
1. EXTRACT   : Telemetria GPS de origens, destinos, pesos de carga e prazos de entrega.
2. TRANSFORM : Validação e Auto-Healing de coordenadas, cálculo geodésico Haversine e
               distância rodoviária estimada, azimute, indexação Geohash-6, geometrias WKT,
               densidade regional de entregas (entregas/1.000 km²) e Índice de Gargalo Logístico (LBI).
3. LOAD      : Persistência estruturada em banco relacional SQLite (`geo_logistics_dw.db`),
               Views SQL para mapas gerenciais, exportação GeoJSON/CSV/Parquet e Relatório Executivo.
"""

from __future__ import annotations

import argparse
import shutil
import time
from typing import Dict, Any

from src.config import (
    DATA_DIR,
    MAP_EXPORTS_DIR,
    RAW_TELEMETRY_DIR,
    REPORTS_DIR,
    SILVER_ENRICHED_DIR,
    SQLITE_DB_PATH,
    ensure_directories,
)
from src.geo_extractor import GeospatialLogisticsExtractor, save_raw_telemetry_csvs
from src.geo_loader import (
    export_map_layers_and_geojson,
    generate_geospatial_executive_report,
    load_to_sqlite_warehouse,
)
from src.geo_transformer import GeospatialLogisticsTransformer


def run_geo_etl_pipeline(
    clean: bool = False,
    seed: int = 42,
    total_shipments: int = 960,
) -> Dict[str, Any]:
    start_ts = time.perf_counter()

    if clean:
        for d in (DATA_DIR, REPORTS_DIR):
            if d.exists():
                shutil.rmtree(d)

    ensure_directories()

    print("=" * 86)
    print("  PROJETO 12: PIPELINE ETL DE DADOS GEOESPACIAIS E INTELIGÊNCIA LOGÍSTICA")
    print("=" * 86)

    # 1. EXTRACT
    print("\n[1/3] EXTRACT: Extraindo telemetria GPS de origens, destinos, cargas e SLAs...")
    extractor = GeospatialLogisticsExtractor(seed=seed)
    raw_batches = extractor.generate_raw_batches(total_shipments=total_shipments)
    save_raw_telemetry_csvs(raw_batches, output_dir=RAW_TELEMETRY_DIR)
    print(f"      - Hubs Logísticos extraídos : {len(raw_batches['raw_hubs'])}")
    print(f"      - Remessas brutas extraídas : {len(raw_batches['raw_shipments']):,}")

    # 2. TRANSFORM
    print("\n[2/3] TRANSFORM: Calculando distâncias Haversine/Rodoviária, Geohash, WKT e Gargalos...")
    transformer = GeospatialLogisticsTransformer()
    transformed = transformer.transform(
        raw_batches["raw_hubs"], raw_batches["raw_shipments"]
    )
    for tbl_name, rows in transformed.items():
        print(f"      - {tbl_name:<33}: {len(rows):>5,} registros")

    # 3. LOAD
    print("\n[3/3] LOAD: Persistindo no SQLite Warehouse, gerando GeoJSON e Relatório Executivo...")
    db_counts = load_to_sqlite_warehouse(transformed, db_path=SQLITE_DB_PATH)
    exported_files = export_map_layers_and_geojson(
        transformed,
        db_path=SQLITE_DB_PATH,
        silver_dir=SILVER_ENRICHED_DIR,
        map_dir=MAP_EXPORTS_DIR,
    )
    report_path, kpis = generate_geospatial_executive_report(transformed)

    elapsed = time.perf_counter() - start_ts

    print("\n" + "=" * 86)
    print("  SUMÁRIO EXECUTIVO GEOESPACIAL & DIAGNÓSTICO DE GARGALOS LOGÍSTICOS")
    print("=" * 86)
    print(f"  * Remessas Válidas Persistidas (Gold)   : {kpis['total_valid_shipments']:,}")
    print(f"  * Coordenadas Invertidas Auto-Corrigidas: {kpis['auto_healed_swapped_coords']}")
    print(f"  * Anomalias Bloqueadas na Quarentena    : {kpis['total_quarantined_anomalies']}")
    print(f"  * Peso Total Movimentado                : {kpis['total_cargo_tons']:,.2f} toneladas")
    print(f"  * Momento de Transporte Total (TKU)     : {kpis['total_freight_moment_t_km']:,.2f} t·km")
    print("-" * 86)
    print(f"  * Distância Geodésica Média (Haversine) : {kpis['avg_haversine_distance_km']:,.2f} km")
    print(f"  * Distância Rodoviária Estimada Média   : {kpis['avg_estimated_road_distance_km']:,.2f} km")
    print(f"  * Velocidade Efetiva Média de Trânsito  : {kpis['avg_effective_speed_kmh']:,.2f} km/h")
    print(f"  * Taxa Global OTIF (No Prazo)           : {kpis['global_otif_pct']:.2f}%")
    print(f"  * Taxa Global de Violação de SLA        : {kpis['global_sla_breach_pct']:.2f}%")
    print(f"  * Corredores com Gargalo Crítico        : {kpis['critical_corridors_count']} corredores")
    print("-" * 86)
    print(f"  * Banco Relacional SQLite               : {SQLITE_DB_PATH}")
    print(f"  * Camada GeoJSON para Mapas Gerenciais  : {exported_files['geojson_map']}")
    print(f"  * Relatório Executivo Markdown          : {report_path}")
    print("=" * 86)
    print(f"Pipeline ETL Geoespacial concluído com sucesso em {elapsed:.2f}s.\n")

    return {
        "db_counts": db_counts,
        "kpis": kpis,
        "exported_files": exported_files,
        "report_path": str(report_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa o pipeline ETL de Dados Geoespaciais e Logísticos."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Limpa os diretórios de saída antes de executar o pipeline.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed aleatória para reprodutibilidade determinística (padrão: 42).",
    )
    args = parser.parse_args()
    run_geo_etl_pipeline(clean=args.clean, seed=args.seed)


if __name__ == "__main__":
    main()
