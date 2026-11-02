"""
Módulo de Carga Relacional Geoespacial e Exportação para Mapas Gerenciais (Stage 3 - Load).

Responsabilidades:
1. Persistir os dados tratados no banco relacional SQLite (`geo_logistics_dw.db`) com tabelas
   dimensionais, fatos, marts de densidade/gargalo, quarentena de anomalias e Views SQL para mapas.
2. Exportar camadas tabulares (CSV/Parquet) e um arquivo **GeoJSON RFC 7946** (`Point` + `LineString`)
   pronto para visualização em Kepler.gl, QGIS, Power BI (Azure Maps / Icon Map) e Deck.gl.
3. Gerar o Relatório Executivo de Inteligência Geoespacial e Gargalos Logísticos em Markdown.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any

import pandas as pd

from src.config import (
    MAP_EXPORTS_DIR,
    REPORTS_DIR,
    SILVER_ENRICHED_DIR,
    SQLITE_DB_PATH,
    ensure_directories,
)


def load_to_sqlite_warehouse(
    transformed: Dict[str, List[Dict[str, Any]]],
    db_path: Path = SQLITE_DB_PATH,
) -> Dict[str, int]:
    """
    Cria o schema relacional otimizado para visualização em mapas gerenciais
    e carrega todas as tabelas tratadas no SQLite.
    """
    ensure_directories()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            PRAGMA foreign_keys = ON;

            DROP VIEW IF EXISTS vw_map_flow_arcs;
            DROP VIEW IF EXISTS vw_map_heatmap_grid_cells;

            DROP TABLE IF EXISTS quarantine_spatial_anomalies;
            DROP TABLE IF EXISTS mart_corridor_bottlenecks;
            DROP TABLE IF EXISTS mart_regional_delivery_density;
            DROP TABLE IF EXISTS fact_shipments_geospatial;
            DROP TABLE IF EXISTS dim_logistics_hubs;

            CREATE TABLE dim_logistics_hubs (
                hub_id TEXT PRIMARY KEY,
                hub_name TEXT NOT NULL,
                city TEXT NOT NULL,
                state_uf TEXT NOT NULL,
                macro_region TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                dock_capacity_tons_day REAL NOT NULL,
                avg_dock_dwell_hours REAL NOT NULL,
                hub_geohash TEXT NOT NULL,
                spatial_grid_cell TEXT NOT NULL,
                geom_wkt_point TEXT NOT NULL
            );

            CREATE TABLE fact_shipments_geospatial (
                shipment_id TEXT PRIMARY KEY,
                corridor_id TEXT NOT NULL,
                origin_hub_id TEXT NOT NULL,
                origin_city TEXT NOT NULL,
                origin_uf TEXT NOT NULL,
                origin_macro_region TEXT NOT NULL,
                origin_latitude REAL NOT NULL,
                origin_longitude REAL NOT NULL,
                origin_geohash TEXT NOT NULL,
                dest_zone_id TEXT NOT NULL,
                dest_city TEXT NOT NULL,
                dest_uf TEXT NOT NULL,
                dest_macro_region TEXT NOT NULL,
                dest_zone_area_km2 REAL NOT NULL,
                dest_latitude REAL NOT NULL,
                dest_longitude REAL NOT NULL,
                dest_geohash TEXT NOT NULL,
                dest_spatial_grid TEXT NOT NULL,
                coordinate_quality_status TEXT NOT NULL,
                haversine_distance_km REAL NOT NULL,
                road_circuity_factor REAL NOT NULL,
                estimated_road_distance_km REAL NOT NULL,
                haul_distance_band TEXT NOT NULL,
                azimuth_degrees REAL NOT NULL,
                compass_direction TEXT NOT NULL,
                vehicle_modal TEXT NOT NULL,
                cargo_category TEXT NOT NULL,
                cargo_weight_kg REAL NOT NULL,
                cargo_weight_tons REAL NOT NULL,
                cargo_volume_m3 REAL NOT NULL,
                cargo_value_brl REAL NOT NULL,
                freight_moment_t_km REAL NOT NULL,
                estimated_freight_cost_brl REAL NOT NULL,
                estimated_co2_kg REAL NOT NULL,
                dispatch_timestamp TEXT NOT NULL,
                promised_delivery_timestamp TEXT NOT NULL,
                actual_delivery_timestamp TEXT NOT NULL,
                promised_sla_hours REAL NOT NULL,
                actual_delivery_hours REAL NOT NULL,
                origin_dock_dwell_hours REAL NOT NULL,
                sla_variance_hours REAL NOT NULL,
                otif_flag INTEGER NOT NULL,
                sla_status TEXT NOT NULL,
                effective_speed_kmh REAL NOT NULL,
                reported_bottleneck_cause TEXT NOT NULL,
                shipment_bottleneck_score REAL NOT NULL,
                geom_origin_wkt TEXT NOT NULL,
                geom_dest_wkt TEXT NOT NULL,
                geom_route_wkt TEXT NOT NULL,
                FOREIGN KEY (origin_hub_id) REFERENCES dim_logistics_hubs(hub_id)
            );

            CREATE TABLE mart_regional_delivery_density (
                dest_zone_id TEXT PRIMARY KEY,
                dest_city TEXT NOT NULL,
                dest_uf TEXT NOT NULL,
                dest_macro_region TEXT NOT NULL,
                zone_area_km2 REAL NOT NULL,
                centroid_latitude REAL NOT NULL,
                centroid_longitude REAL NOT NULL,
                centroid_geohash TEXT NOT NULL,
                total_shipments INTEGER NOT NULL,
                total_cargo_tons REAL NOT NULL,
                total_cargo_value_brl REAL NOT NULL,
                total_freight_moment_t_km REAL NOT NULL,
                delivery_density_shipments_per_1000km2 REAL NOT NULL,
                cargo_density_tons_per_km2 REAL NOT NULL,
                otif_rate_pct REAL NOT NULL,
                sla_breach_rate_pct REAL NOT NULL,
                avg_delay_when_late_hours REAL NOT NULL,
                regional_bottleneck_index REAL NOT NULL,
                density_tier TEXT NOT NULL,
                geom_centroid_wkt TEXT NOT NULL
            );

            CREATE TABLE mart_corridor_bottlenecks (
                corridor_id TEXT PRIMARY KEY,
                origin_hub_id TEXT NOT NULL,
                origin_city TEXT NOT NULL,
                origin_uf TEXT NOT NULL,
                dest_zone_id TEXT NOT NULL,
                dest_city TEXT NOT NULL,
                dest_uf TEXT NOT NULL,
                dest_macro_region TEXT NOT NULL,
                origin_latitude REAL NOT NULL,
                origin_longitude REAL NOT NULL,
                dest_latitude REAL NOT NULL,
                dest_longitude REAL NOT NULL,
                shipments_count INTEGER NOT NULL,
                total_cargo_tons REAL NOT NULL,
                avg_haversine_km REAL NOT NULL,
                avg_road_distance_km REAL NOT NULL,
                avg_promised_sla_hours REAL NOT NULL,
                avg_actual_delivery_hours REAL NOT NULL,
                avg_dock_dwell_hours REAL NOT NULL,
                avg_effective_speed_kmh REAL NOT NULL,
                sla_breach_rate_pct REAL NOT NULL,
                corridor_bottleneck_index REAL NOT NULL,
                bottleneck_severity TEXT NOT NULL,
                primary_bottleneck_cause TEXT NOT NULL,
                geom_corridor_wkt TEXT NOT NULL,
                FOREIGN KEY (origin_hub_id) REFERENCES dim_logistics_hubs(hub_id)
            );

            CREATE TABLE quarantine_spatial_anomalies (
                shipment_id TEXT PRIMARY KEY,
                origin_hub_id TEXT NOT NULL,
                dest_zone_id TEXT NOT NULL,
                raw_origin_lat REAL NOT NULL,
                raw_origin_lon REAL NOT NULL,
                raw_dest_lat REAL NOT NULL,
                raw_dest_lon REAL NOT NULL,
                cargo_weight_kg REAL NOT NULL,
                anomaly_reason TEXT NOT NULL,
                dispatch_timestamp TEXT NOT NULL
            );

            CREATE INDEX idx_shipments_corridor ON fact_shipments_geospatial(corridor_id, sla_status);
            CREATE INDEX idx_shipments_dest_grid ON fact_shipments_geospatial(dest_spatial_grid, dest_geohash);
            CREATE INDEX idx_shipments_region ON fact_shipments_geospatial(dest_macro_region, dest_uf);

            -- View 1: Camada de Arcos de Fluxo (Origin-Destination Flow Map Layer)
            CREATE VIEW vw_map_flow_arcs AS
            SELECT
                c.corridor_id,
                h.hub_name AS origin_hub_name,
                c.origin_city || '/' || c.origin_uf AS origin_label,
                c.dest_city || '/' || c.dest_uf AS dest_label,
                c.dest_macro_region,
                c.origin_latitude,
                c.origin_longitude,
                c.dest_latitude,
                c.dest_longitude,
                c.shipments_count,
                c.total_cargo_tons,
                c.avg_haversine_km,
                c.avg_road_distance_km,
                c.avg_effective_speed_kmh,
                c.sla_breach_rate_pct,
                c.corridor_bottleneck_index,
                c.bottleneck_severity,
                c.primary_bottleneck_cause,
                c.geom_corridor_wkt,
                CASE c.bottleneck_severity
                    WHEN 'CRITICAL_BOTTLENECK' THEN '#DC2626'
                    WHEN 'MODERATE_CONGESTION' THEN '#D97706'
                    ELSE '#16A34A'
                END AS map_hex_color
            FROM mart_corridor_bottlenecks c
            INNER JOIN dim_logistics_hubs h ON c.origin_hub_id = h.hub_id
            ORDER BY c.corridor_bottleneck_index DESC;

            -- View 2: Camada de Mapa de Calor por Quadrícula Espacial (Spatial Grid Heatmap Layer)
            CREATE VIEW vw_map_heatmap_grid_cells AS
            SELECT
                dest_spatial_grid,
                dest_macro_region,
                dest_uf,
                COUNT(*) AS shipments_count,
                ROUND(AVG(dest_latitude), 6) AS grid_centroid_lat,
                ROUND(AVG(dest_longitude), 6) AS grid_centroid_lon,
                ROUND(SUM(cargo_weight_tons), 2) AS total_cargo_tons,
                ROUND(AVG(haversine_distance_km), 2) AS avg_haversine_km,
                ROUND(AVG(estimated_road_distance_km), 2) AS avg_road_km,
                ROUND((1.0 - AVG(CAST(otif_flag AS REAL))) * 100.0, 2) AS sla_breach_pct,
                ROUND(AVG(shipment_bottleneck_score), 2) AS avg_bottleneck_score
            FROM fact_shipments_geospatial
            GROUP BY dest_spatial_grid, dest_macro_region, dest_uf
            ORDER BY shipments_count DESC;
            """
        )

        counts: Dict[str, int] = {}
        for table_name, rows in transformed.items():
            if not rows:
                counts[table_name] = 0
                continue
            cols = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"
            cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
            counts[table_name] = len(rows)

        conn.commit()
        return counts
    finally:
        conn.close()


def export_map_layers_and_geojson(
    transformed: Dict[str, List[Dict[str, Any]]],
    db_path: Path = SQLITE_DB_PATH,
    silver_dir: Path = SILVER_ENRICHED_DIR,
    map_dir: Path = MAP_EXPORTS_DIR,
) -> Dict[str, str]:
    """
    Exporta os dados tratados em CSV/Parquet e constrói o arquivo GeoJSON RFC 7946
    (`logistics_corridors_and_bottlenecks.geojson`) com feições Point e LineString.
    """
    silver_dir.mkdir(parents=True, exist_ok=True)
    map_dir.mkdir(parents=True, exist_ok=True)

    exported_files: Dict[str, str] = {}

    for table_name, rows in transformed.items():
        if not rows:
            continue
        csv_path = map_dir / f"{table_name}.csv"
        parquet_path = silver_dir / f"{table_name}.parquet"

        fieldnames = list(rows[0].keys())
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        pd.DataFrame(rows).to_parquet(parquet_path, index=False)
        exported_files[f"{table_name}_csv"] = str(csv_path)
        exported_files[f"{table_name}_parquet"] = str(parquet_path)

    # Exporta também as 2 Views SQL de Mapas Gerenciais em CSV
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        for view_name in ("vw_map_flow_arcs", "vw_map_heatmap_grid_cells"):
            cur.execute(f"SELECT * FROM {view_name}")
            v_rows = [dict(r) for r in cur.fetchall()]
            if v_rows:
                v_csv = map_dir / f"{view_name}.csv"
                with open(v_csv, mode="w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(v_rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(v_rows)
                exported_files[view_name] = str(v_csv)
    finally:
        conn.close()

    # Construção do GeoJSON FeatureCollection RFC 7946
    features: List[Dict[str, Any]] = []

    # 1. Feições Point para Hubs de Origem
    for hub in transformed["dim_logistics_hubs"]:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [hub["longitude"], hub["latitude"]],
                },
                "properties": {
                    "feature_layer": "ORIGIN_HUB",
                    "id": hub["hub_id"],
                    "name": hub["hub_name"],
                    "city": hub["city"],
                    "state_uf": hub["state_uf"],
                    "macro_region": hub["macro_region"],
                    "dock_capacity_tons_day": hub["dock_capacity_tons_day"],
                    "geohash": hub["hub_geohash"],
                },
            }
        )

    # 2. Feições Point para Centroides de Densidade Regional
    for reg in transformed["mart_regional_delivery_density"]:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [reg["centroid_longitude"], reg["centroid_latitude"]],
                },
                "properties": {
                    "feature_layer": "REGIONAL_DENSITY_CENTROID",
                    "id": reg["dest_zone_id"],
                    "city": reg["dest_city"],
                    "state_uf": reg["dest_uf"],
                    "macro_region": reg["dest_macro_region"],
                    "total_shipments": reg["total_shipments"],
                    "total_cargo_tons": reg["total_cargo_tons"],
                    "delivery_density_per_1000km2": reg["delivery_density_shipments_per_1000km2"],
                    "otif_rate_pct": reg["otif_rate_pct"],
                    "regional_bottleneck_index": reg["regional_bottleneck_index"],
                    "density_tier": reg["density_tier"],
                },
            }
        )

    # 3. Feições LineString para Corredores Logísticos e Gargalos
    for corr in transformed["mart_corridor_bottlenecks"]:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [corr["origin_longitude"], corr["origin_latitude"]],
                        [corr["dest_longitude"], corr["dest_latitude"]],
                    ],
                },
                "properties": {
                    "feature_layer": "LOGISTICS_CORRIDOR",
                    "corridor_id": corr["corridor_id"],
                    "origin_city": corr["origin_city"],
                    "dest_city": corr["dest_city"],
                    "dest_macro_region": corr["dest_macro_region"],
                    "shipments_count": corr["shipments_count"],
                    "total_cargo_tons": corr["total_cargo_tons"],
                    "avg_haversine_km": corr["avg_haversine_km"],
                    "avg_road_distance_km": corr["avg_road_distance_km"],
                    "avg_effective_speed_kmh": corr["avg_effective_speed_kmh"],
                    "sla_breach_rate_pct": corr["sla_breach_rate_pct"],
                    "corridor_bottleneck_index": corr["corridor_bottleneck_index"],
                    "bottleneck_severity": corr["bottleneck_severity"],
                    "primary_bottleneck_cause": corr["primary_bottleneck_cause"],
                },
            }
        )

    geojson_payload = {
        "type": "FeatureCollection",
        "name": "brazil_logistics_corridors_and_bottlenecks",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    geojson_path = map_dir / "logistics_corridors_and_bottlenecks.geojson"
    geojson_path.write_text(
        json.dumps(geojson_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    exported_files["geojson_map"] = str(geojson_path)

    return exported_files


def generate_geospatial_executive_report(
    transformed: Dict[str, List[Dict[str, Any]]],
    report_path: Path = REPORTS_DIR / "geospatial_logistics_report.md",
) -> Tuple[Path, Dict[str, Any]]:
    """Calcula KPIs globais e gera o Relatório Executivo Markdown de Logística Geoespacial."""
    report_path.parent.mkdir(parents=True, exist_ok=True)

    shipments = transformed["fact_shipments_geospatial"]
    density_rows = transformed["mart_regional_delivery_density"]
    corridors = transformed["mart_corridor_bottlenecks"]
    quarantine = transformed["quarantine_spatial_anomalies"]

    total_valid = len(shipments)
    total_quarantined = len(quarantine)
    auto_healed_count = sum(
        1 for s in shipments if s["coordinate_quality_status"] == "AUTO_HEALED_SWAPPED_LATLON"
    )

    total_tons = round(sum(s["cargo_weight_tons"] for s in shipments), 2)
    total_t_km = round(sum(s["freight_moment_t_km"] for s in shipments), 2)
    total_freight_cost_brl = round(sum(s["estimated_freight_cost_brl"] for s in shipments), 2)
    total_co2_kg = round(sum(s["estimated_co2_kg"] for s in shipments), 2)

    avg_hav_km = round(sum(s["haversine_distance_km"] for s in shipments) / total_valid, 2)
    avg_road_km = round(sum(s["estimated_road_distance_km"] for s in shipments) / total_valid, 2)
    avg_speed_kmh = round(sum(s["effective_speed_kmh"] for s in shipments) / total_valid, 2)
    otif_pct = round((sum(s["otif_flag"] for s in shipments) / total_valid) * 100.0, 2)
    sla_breach_pct = round(100.0 - otif_pct, 2)

    critical_corridors = [
        c for c in corridors if c["bottleneck_severity"] == "CRITICAL_BOTTLENECK"
    ]

    kpis = {
        "total_valid_shipments": total_valid,
        "total_quarantined_anomalies": total_quarantined,
        "auto_healed_swapped_coords": auto_healed_count,
        "total_cargo_tons": total_tons,
        "total_freight_moment_t_km": total_t_km,
        "total_freight_cost_brl": total_freight_cost_brl,
        "total_co2_tons": round(total_co2_kg / 1000.0, 2),
        "avg_haversine_distance_km": avg_hav_km,
        "avg_estimated_road_distance_km": avg_road_km,
        "avg_effective_speed_kmh": avg_speed_kmh,
        "global_otif_pct": otif_pct,
        "global_sla_breach_pct": sla_breach_pct,
        "critical_corridors_count": len(critical_corridors),
    }

    lines = [
        "# Relatório Executivo: ETL Geoespacial, Densidade de Entregas e Gargalos Logísticos",
        "",
        "## 1. Sumário Executivo da Malha Logística Nacional",
        "",
        "| Indicador Geoespacial / Logístico | Valor Consolidado | Observação Técnica |",
        "| :--- | ---: | :--- |",
        f"| **Remessas Válidas Processadas (Gold)** | `{total_valid:,}` | Coordenadas validadas em WGS-84 |",
        f"| **Coordenadas Invertidas Recuperadas (Auto-Healed)** | `{auto_healed_count}` | Correção automática Lat/Lon Swap |",
        f"| **Registros em Quarentena Espacial** | `{total_quarantined}` | Null Island `(0,0)` ou fora do Bounding Box |",
        f"| **Peso Total Transportado** | `{total_tons:,.2f} t` | Carga líquida movimentada |",
        f"| **Momento de Transporte Total (TKU)** | `{total_t_km:,.2f} t·km` | Tonelada-quilômetro útil rodoviária |",
        f"| **Distância Geodésica Média (Haversine)** | `{avg_hav_km:,.2f} km` | Linha reta esférica sobre WGS-84 |",
        f"| **Distância Rodoviária Estimada Média** | `{avg_road_km:,.2f} km` | Ajustada pelo índice de tortuosidade ($\\kappa$) |",
        f"| **Velocidade Efetiva Média de Trânsito** | `{avg_speed_kmh:,.2f} km/h` | Descontado tempo de pátio/doca |",
        f"| **Taxa Global OTIF (On-Time In-Full)** | `{otif_pct:.2f}%` | Entregas dentro do SLA prometido |",
        f"| **Taxa Global de Violação de SLA** | `{sla_breach_pct:.2f}%` | Remessas impactadas por gargalos |",
        f"| **Custo Operacional Estimado de Frete** | `R$ {total_freight_cost_brl:,.2f}` | Baseado em R$/t·km por modal |",
        f"| **Pegada de Carbono Estimada (Escopo 1/3)** | `{kpis['total_co2_tons']:,.2f} t CO2e` | Emissões do transporte de cargas |",
        "",
        "---",
        "",
        "## 2. Densidade de Entregas por Polo Regional (Top 14 Zonas)",
        "",
        "| Zona ID | Polo / Cidade | UF | Região | Área (km²) | Entregas | Carga (t) | Densidade (Entregas / 1.000 km²) | Densidade Carga (t/km²) | OTIF % | LBI Regional | Classificação Espacial |",
        "| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
    ]

    for r in density_rows:
        lines.append(
            f"| `{r['dest_zone_id']}` | **{r['dest_city']}** | {r['dest_uf']} | {r['dest_macro_region']} | "
            f"{r['zone_area_km2']:,.0f} | {r['total_shipments']} | {r['total_cargo_tons']:,.1f} | "
            f"**`{r['delivery_density_shipments_per_1000km2']:,.2f}`** | {r['cargo_density_tons_per_km2']:.3f} | "
            f"`{r['otif_rate_pct']:.1f}%` | `{r['regional_bottleneck_index']:.1f}` | {r['density_tier']} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Ranking de Gargalos Logísticos por Corredor (Top 15 Rotas Críticas)",
            "",
            "| Corredor ID | Origem -> Destino | Região Destino | Viagens | Haversine (km) | Rodoviário (km) | Doca (h) | Vel. Efetiva (km/h) | Violação SLA % | Índice Gargalo (LBI) | Severidade | Causa Raiz Predominante |",
            "| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | :--- |",
        ]
    )

    for c in corridors[:15]:
        lines.append(
            f"| `{c['corridor_id']}` | {c['origin_city']}/{c['origin_uf']} → **{c['dest_city']}/{c['dest_uf']}** | "
            f"{c['dest_macro_region']} | {c['shipments_count']} | {c['avg_haversine_km']:,.1f} | "
            f"{c['avg_road_distance_km']:,.1f} | {c['avg_dock_dwell_hours']:.1f}h | "
            f"{c['avg_effective_speed_kmh']:.1f} | `{c['sla_breach_rate_pct']:.1f}%` | "
            f"**`{c['corridor_bottleneck_index']:.2f}`** | `{c['bottleneck_severity']}` | {c['primary_bottleneck_cause']} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Auditoria de Quarentena Geoespacial (Anomalias Bloqueadas)",
            "",
            "| Shipment ID | Hub Origem | Zona Destino | Lat Destino Bruta | Lon Destino Bruta | Peso (kg) | Motivo de Bloqueio |",
            "| :--- | :--- | :--- | ---: | ---: | ---: | :--- |",
        ]
    )

    for q in quarantine:
        lines.append(
            f"| `{q['shipment_id']}` | `{q['origin_hub_id']}` | `{q['dest_zone_id']}` | "
            f"{q['raw_dest_lat']} | {q['raw_dest_lon']} | {q['cargo_weight_kg']:,.1f} | "
            f"`{q['anomaly_reason']}` |"
        )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path, kpis
