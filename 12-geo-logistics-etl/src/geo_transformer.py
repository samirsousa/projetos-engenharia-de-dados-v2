"""
Motor de Transformação Geoespacial e Diagnóstico de Gargalos Logísticos (Stage 2 - Transform).

Implementa:
1. Validação Geodésica & Auto-Healing de Coordenadas Invertidas (Lat/Lon Swap) + Quarentena.
2. Matemática Esférica / Geodésica:
   - Distância de Grande Círculo (Fórmula de Haversine em WGS-84).
   - Distância Rodoviária Estimada (aplicação do índice de tortuosidade viária regional).
   - Azimute Inicial (Forward Bearing 0°-360°) e Rosa dos Ventos (8 direções cardeais).
   - Indexação Espacial Geohash-6 (Base32) e Grade Espacial (Spatial Grid Cell).
   - Geometrias OGC Well-Known Text (`POINT` e `LINESTRING`) para visualização em mapas.
3. Cálculo de Densidade Regional de Entregas (entregas/1.000 km² e toneladas/km²) e
   Índice de Gargalo Logístico (Logistics Bottleneck Index - LBI 0..100).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Dict, List, Any, Tuple

from src.config import BRAZIL_BBOX, EARTH_RADIUS_KM, VEHICLE_MODALS

_GEOHASH_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
_CARDINAL_DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def is_within_brazil_bbox(lat: float, lon: float) -> bool:
    """Verifica se o par (latitude, longitude) está contido nos limites territoriais do Brasil."""
    return (
        BRAZIL_BBOX["min_lat"] <= lat <= BRAZIL_BBOX["max_lat"]
        and BRAZIL_BBOX["min_lon"] <= lon <= BRAZIL_BBOX["max_lon"]
    )


def validate_and_heal_coordinates(
    lat: float, lon: float
) -> Tuple[bool, float, float, str]:
    """
    Valida um par de coordenadas GPS.
    Se (lat, lon) estiver invertido (ex: lon no lugar de lat), realiza Auto-Healing.
    Retorna: (is_valid, healed_lat, healed_lon, quality_status).
    """
    if lat == 0.0 and lon == 0.0:
        return False, lat, lon, "QUARANTINED_NULL_ISLAND_ZERO_COORD"

    if is_within_brazil_bbox(lat, lon):
        return True, lat, lon, "VALID_ORIGINAL"

    # Testa se houve inversão acidental entre Latitude e Longitude na telemetria
    if is_within_brazil_bbox(lon, lat):
        return True, lon, lat, "AUTO_HEALED_SWAPPED_LATLON"

    return False, lat, lon, "QUARANTINED_OUT_OF_BRAZIL_BOUNDS"


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula a distância geodésica de grande círculo (Haversine) em quilômetros
    entre dois pontos (lat1, lon1) e (lat2, lon2) sobre a esfera média WGS-84.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return round(EARTH_RADIUS_KM * c, 2)


def forward_azimuth_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula o azimute inicial (Forward Bearing) em graus [0.0, 360.0)
    do ponto de origem para o ponto de destino.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    x = math.sin(delta_lambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - (
        math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    )
    initial_bearing = math.degrees(math.atan2(x, y))
    return round((initial_bearing + 360.0) % 360.0, 2)


def azimuth_to_cardinal(azimuth_deg: float) -> str:
    """Converte o azimute em graus para uma das 8 direções cardeais/colaterais."""
    idx = int(round(azimuth_deg / 45.0)) % 8
    return _CARDINAL_DIRS[idx]


def encode_geohash(latitude: float, longitude: float, precision: int = 6) -> str:
    """
    Codifica (latitude, longitude) em uma string Geohash Base32 determinística.
    Permite indexação espacial hierárquica e agregação em mapas sem dependências externas C.
    """
    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]
    geohash: List[str] = []
    bits = [16, 8, 4, 2, 1]
    bit = 0
    ch = 0
    even = True

    while len(geohash) < precision:
        if even:
            mid = (lon_interval[0] + lon_interval[1]) / 2.0
            if longitude > mid:
                ch |= bits[bit]
                lon_interval[0] = mid
            else:
                lon_interval[1] = mid
        else:
            mid = (lat_interval[0] + lat_interval[1]) / 2.0
            if latitude > mid:
                ch |= bits[bit]
                lat_interval[0] = mid
            else:
                lat_interval[1] = mid

        even = not even
        if bit < 4:
            bit += 1
        else:
            geohash.append(_GEOHASH_BASE32[ch])
            bit = 0
            ch = 0

    return "".join(geohash)


def encode_spatial_grid_cell(latitude: float, longitude: float, step_deg: float = 1.0) -> str:
    """Gera identificador de quadrícula espacial de 1°x1° para mapas de calor gerenciais."""
    lat_bucket = int(math.floor(latitude / step_deg) * step_deg)
    lon_bucket = int(math.floor(longitude / step_deg) * step_deg)
    ns = "S" if lat_bucket < 0 else "N"
    ew = "W" if lon_bucket < 0 else "E"
    return f"GRID_{ns}{abs(lat_bucket):02d}_{ew}{abs(lon_bucket):03d}"


def make_wkt_point(longitude: float, latitude: float) -> str:
    """Retorna geometria OGC Well-Known Text POINT(lon lat)."""
    return f"POINT ({longitude:.6f} {latitude:.6f})"


def make_wkt_linestring(lon1: float, lat1: float, lon2: float, lat2: float) -> str:
    """Retorna geometria OGC Well-Known Text LINESTRING(lon1 lat1, lon2 lat2)."""
    return f"LINESTRING ({lon1:.6f} {lat1:.6f}, {lon2:.6f} {lat2:.6f})"


class GeospatialLogisticsTransformer:
    """Executa o enriquecimento geoespacial, cálculo de densidade regional e detecção de gargalos."""

    def transform(
        self,
        raw_hubs: List[Dict[str, Any]],
        raw_shipments: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        dim_hubs: List[Dict[str, Any]] = []
        for h in raw_hubs:
            dim_hubs.append(
                {
                    **h,
                    "hub_geohash": encode_geohash(h["latitude"], h["longitude"], precision=6),
                    "spatial_grid_cell": encode_spatial_grid_cell(h["latitude"], h["longitude"]),
                    "geom_wkt_point": make_wkt_point(h["longitude"], h["latitude"]),
                }
            )

        enriched_shipments: List[Dict[str, Any]] = []
        quarantined_anomalies: List[Dict[str, Any]] = []

        for row in raw_shipments:
            o_ok, o_lat, o_lon, o_status = validate_and_heal_coordinates(
                float(row["origin_latitude"]), float(row["origin_longitude"])
            )
            d_ok, d_lat, d_lon, d_status = validate_and_heal_coordinates(
                float(row["dest_latitude"]), float(row["dest_longitude"])
            )

            weight_kg = float(row["cargo_weight_kg"])
            if not o_ok or not d_ok or weight_kg <= 0.0:
                quarantined_anomalies.append(
                    {
                        "shipment_id": row["shipment_id"],
                        "origin_hub_id": row["origin_hub_id"],
                        "dest_zone_id": row["dest_zone_id"],
                        "raw_origin_lat": row["origin_latitude"],
                        "raw_origin_lon": row["origin_longitude"],
                        "raw_dest_lat": row["dest_latitude"],
                        "raw_dest_lon": row["dest_longitude"],
                        "cargo_weight_kg": weight_kg,
                        "anomaly_reason": d_status if not d_ok else o_status,
                        "dispatch_timestamp": row["dispatch_timestamp"],
                    }
                )
                continue

            coord_quality = (
                "AUTO_HEALED_SWAPPED_LATLON"
                if "AUTO_HEALED_SWAPPED_LATLON" in (o_status, d_status)
                else "VALID_ORIGINAL"
            )

            hav_km = haversine_distance_km(o_lat, o_lon, d_lat, d_lon)
            circuity = float(row["road_circuity_factor"])
            est_road_km = round(hav_km * circuity, 2)
            azimuth_deg = forward_azimuth_degrees(o_lat, o_lon, d_lat, d_lon)
            compass_dir = azimuth_to_cardinal(azimuth_deg)

            origin_geohash = encode_geohash(o_lat, o_lon, precision=6)
            dest_geohash = encode_geohash(d_lat, d_lon, precision=6)
            dest_grid_cell = encode_spatial_grid_cell(d_lat, d_lon)

            modal_key = row["vehicle_modal"]
            modal_meta = VEHICLE_MODALS[modal_key]

            cargo_tons = round(weight_kg / 1000.0, 4)
            freight_moment_t_km = round(cargo_tons * est_road_km, 2)
            freight_cost_brl = round(freight_moment_t_km * modal_meta["cost_per_t_km_brl"], 2)
            co2_emissions_kg = round(freight_moment_t_km * modal_meta["co2_kg_per_t_km"], 2)

            promised_hours = float(row["promised_sla_hours"])
            actual_hours = float(row["actual_delivery_hours"])
            dock_dwell_hours = float(row["origin_dock_dwell_hours"])
            net_driving_hours = max(0.5, actual_hours - dock_dwell_hours)

            effective_speed_kmh = round(est_road_km / net_driving_hours, 2)
            sla_variance_hours = round(actual_hours - promised_hours, 2)
            otif_flag = 1 if sla_variance_hours <= 0.0 else 0

            if sla_variance_hours <= 0.0:
                sla_status = "ON_TIME"
            elif sla_variance_hours <= 6.0:
                sla_status = "MODERATE_DELAY"
            else:
                sla_status = "CRITICAL_DELAY"

            # Cálculo do Score de Gargalo Logístico por Remessa (0 a 100):
            # Combina atraso relativo ao SLA (50%), excesso de tempo de doca > 2.5h (25%)
            # e perda de velocidade média frente à velocidade de cruzeiro do modal (25%).
            delay_ratio = max(0.0, sla_variance_hours / max(1.0, promised_hours))
            delay_component = min(50.0, delay_ratio * 95.0)

            dock_excess = max(0.0, dock_dwell_hours - 2.5)
            dock_component = min(25.0, dock_excess * 5.0)

            speed_deficit = max(
                0.0,
                (modal_meta["avg_cruise_speed_kmh"] - effective_speed_kmh)
                / modal_meta["avg_cruise_speed_kmh"],
            )
            speed_component = min(25.0, speed_deficit * 45.0)

            bottleneck_score = round(delay_component + dock_component + speed_component, 2)

            if hav_km < 150.0:
                haul_distance_band = "1. Curta Distância (< 150 km)"
            elif hav_km < 600.0:
                haul_distance_band = "2. Média Distância (150 a 600 km)"
            elif hav_km < 1400.0:
                haul_distance_band = "3. Longa Distância (600 a 1.400 km)"
            else:
                haul_distance_band = "4. Ultra-Longa Distância (> 1.400 km)"

            enriched_shipments.append(
                {
                    "shipment_id": row["shipment_id"],
                    "corridor_id": f"{row['origin_hub_id']}->{row['dest_zone_id']}",
                    "origin_hub_id": row["origin_hub_id"],
                    "origin_city": row["origin_city"],
                    "origin_uf": row["origin_uf"],
                    "origin_macro_region": row["origin_macro_region"],
                    "origin_latitude": o_lat,
                    "origin_longitude": o_lon,
                    "origin_geohash": origin_geohash,
                    "dest_zone_id": row["dest_zone_id"],
                    "dest_city": row["dest_city"],
                    "dest_uf": row["dest_uf"],
                    "dest_macro_region": row["dest_macro_region"],
                    "dest_zone_area_km2": float(row["dest_zone_area_km2"]),
                    "dest_latitude": d_lat,
                    "dest_longitude": d_lon,
                    "dest_geohash": dest_geohash,
                    "dest_spatial_grid": dest_grid_cell,
                    "coordinate_quality_status": coord_quality,
                    "haversine_distance_km": hav_km,
                    "road_circuity_factor": circuity,
                    "estimated_road_distance_km": est_road_km,
                    "haul_distance_band": haul_distance_band,
                    "azimuth_degrees": azimuth_deg,
                    "compass_direction": compass_dir,
                    "vehicle_modal": modal_key,
                    "cargo_category": row["cargo_category"],
                    "cargo_weight_kg": weight_kg,
                    "cargo_weight_tons": cargo_tons,
                    "cargo_volume_m3": float(row["cargo_volume_m3"]),
                    "cargo_value_brl": float(row["cargo_value_brl"]),
                    "freight_moment_t_km": freight_moment_t_km,
                    "estimated_freight_cost_brl": freight_cost_brl,
                    "estimated_co2_kg": co2_emissions_kg,
                    "dispatch_timestamp": row["dispatch_timestamp"],
                    "promised_delivery_timestamp": row["promised_delivery_timestamp"],
                    "actual_delivery_timestamp": row["actual_delivery_timestamp"],
                    "promised_sla_hours": promised_hours,
                    "actual_delivery_hours": actual_hours,
                    "origin_dock_dwell_hours": dock_dwell_hours,
                    "sla_variance_hours": sla_variance_hours,
                    "otif_flag": otif_flag,
                    "sla_status": sla_status,
                    "effective_speed_kmh": effective_speed_kmh,
                    "reported_bottleneck_cause": row["reported_bottleneck_cause"],
                    "shipment_bottleneck_score": bottleneck_score,
                    "geom_origin_wkt": make_wkt_point(o_lon, o_lat),
                    "geom_dest_wkt": make_wkt_point(d_lon, d_lat),
                    "geom_route_wkt": make_wkt_linestring(o_lon, o_lat, d_lon, d_lat),
                }
            )

        regional_density = self._compute_regional_delivery_density(enriched_shipments)
        corridor_bottlenecks = self._compute_corridor_bottlenecks(enriched_shipments)

        return {
            "dim_logistics_hubs": dim_hubs,
            "fact_shipments_geospatial": enriched_shipments,
            "mart_regional_delivery_density": regional_density,
            "mart_corridor_bottlenecks": corridor_bottlenecks,
            "quarantine_spatial_anomalies": quarantined_anomalies,
        }

    def _compute_regional_delivery_density(
        self, shipments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Agrega as entregas por Zona/Polo Geográfico e calcula métricas de densidade espacial
        (entregas por 1.000 km², toneladas por km², centroide ponderado e índice de gargalo regional).
        """
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for s in shipments:
            grouped[s["dest_zone_id"]].append(s)

        rows: List[Dict[str, Any]] = []
        for zone_id, items in grouped.items():
            sample = items[0]
            area_km2 = sample["dest_zone_area_km2"]
            n_shipments = len(items)
            total_tons = round(sum(x["cargo_weight_tons"] for x in items), 2)
            total_value_brl = round(sum(x["cargo_value_brl"] for x in items), 2)
            total_t_km = round(sum(x["freight_moment_t_km"] for x in items), 2)

            centroid_lat = round(sum(x["dest_latitude"] for x in items) / n_shipments, 6)
            centroid_lon = round(sum(x["dest_longitude"] for x in items) / n_shipments, 6)

            shipments_per_1000km2 = round((n_shipments / area_km2) * 1000.0, 2)
            tons_per_km2 = round(total_tons / area_km2, 4)

            otif_count = sum(x["otif_flag"] for x in items)
            otif_rate_pct = round((otif_count / n_shipments) * 100.0, 2)
            sla_breach_rate_pct = round(100.0 - otif_rate_pct, 2)

            delayed_items = [x["sla_variance_hours"] for x in items if x["sla_variance_hours"] > 0]
            avg_delay_when_late_hours = (
                round(sum(delayed_items) / len(delayed_items), 2) if delayed_items else 0.0
            )
            avg_bottleneck_score = round(
                sum(x["shipment_bottleneck_score"] for x in items) / n_shipments, 2
            )

            if shipments_per_1000km2 >= 75.0:
                density_tier = "HIGH_DENSITY_METROPOLITAN_CORE"
            elif shipments_per_1000km2 >= 40.0:
                density_tier = "MEDIUM_DENSITY_REGIONAL_POLE"
            else:
                density_tier = "LOW_DENSITY_LONG_HAUL_FRONTIER"

            rows.append(
                {
                    "dest_zone_id": zone_id,
                    "dest_city": sample["dest_city"],
                    "dest_uf": sample["dest_uf"],
                    "dest_macro_region": sample["dest_macro_region"],
                    "zone_area_km2": area_km2,
                    "centroid_latitude": centroid_lat,
                    "centroid_longitude": centroid_lon,
                    "centroid_geohash": encode_geohash(centroid_lat, centroid_lon, precision=5),
                    "total_shipments": n_shipments,
                    "total_cargo_tons": total_tons,
                    "total_cargo_value_brl": total_value_brl,
                    "total_freight_moment_t_km": total_t_km,
                    "delivery_density_shipments_per_1000km2": shipments_per_1000km2,
                    "cargo_density_tons_per_km2": tons_per_km2,
                    "otif_rate_pct": otif_rate_pct,
                    "sla_breach_rate_pct": sla_breach_rate_pct,
                    "avg_delay_when_late_hours": avg_delay_when_late_hours,
                    "regional_bottleneck_index": avg_bottleneck_score,
                    "density_tier": density_tier,
                    "geom_centroid_wkt": make_wkt_point(centroid_lon, centroid_lat),
                }
            )

        rows.sort(key=lambda r: r["delivery_density_shipments_per_1000km2"], reverse=True)
        return rows

    def _compute_corridor_bottlenecks(
        self, shipments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Agrega as rotas por Corredor Logístico (Origem -> Destino), identificando
        os principais gargalos de infraestrutura, atraso médio, velocidade efetiva e causa raiz.
        """
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for s in shipments:
            grouped[s["corridor_id"]].append(s)

        corridors: List[Dict[str, Any]] = []
        for corridor_id, items in grouped.items():
            sample = items[0]
            n = len(items)
            o_lat = round(sum(x["origin_latitude"] for x in items) / n, 6)
            o_lon = round(sum(x["origin_longitude"] for x in items) / n, 6)
            d_lat = round(sum(x["dest_latitude"] for x in items) / n, 6)
            d_lon = round(sum(x["dest_longitude"] for x in items) / n, 6)

            avg_hav_km = round(sum(x["haversine_distance_km"] for x in items) / n, 2)
            avg_road_km = round(sum(x["estimated_road_distance_km"] for x in items) / n, 2)
            total_tons = round(sum(x["cargo_weight_tons"] for x in items), 2)
            avg_promised_h = round(sum(x["promised_sla_hours"] for x in items) / n, 2)
            avg_actual_h = round(sum(x["actual_delivery_hours"] for x in items) / n, 2)
            avg_dock_h = round(sum(x["origin_dock_dwell_hours"] for x in items) / n, 2)
            avg_speed_kmh = round(sum(x["effective_speed_kmh"] for x in items) / n, 2)

            sla_breaches = sum(1 for x in items if x["otif_flag"] == 0)
            sla_breach_pct = round((sla_breaches / n) * 100.0, 2)
            corridor_lbi = round(sum(x["shipment_bottleneck_score"] for x in items) / n, 2)

            non_normal_causes = [
                x["reported_bottleneck_cause"]
                for x in items
                if x["reported_bottleneck_cause"] != "Normal Flow"
            ]
            primary_cause = (
                Counter(non_normal_causes).most_common(1)[0][0]
                if non_normal_causes
                else "Normal Flow"
            )

            if corridor_lbi >= 22.0 or sla_breach_pct >= 45.0:
                severity = "CRITICAL_BOTTLENECK"
            elif corridor_lbi >= 12.0 or sla_breach_pct >= 25.0:
                severity = "MODERATE_CONGESTION"
            else:
                severity = "OPTIMAL_CORRIDOR"

            corridors.append(
                {
                    "corridor_id": corridor_id,
                    "origin_hub_id": sample["origin_hub_id"],
                    "origin_city": sample["origin_city"],
                    "origin_uf": sample["origin_uf"],
                    "dest_zone_id": sample["dest_zone_id"],
                    "dest_city": sample["dest_city"],
                    "dest_uf": sample["dest_uf"],
                    "dest_macro_region": sample["dest_macro_region"],
                    "origin_latitude": o_lat,
                    "origin_longitude": o_lon,
                    "dest_latitude": d_lat,
                    "dest_longitude": d_lon,
                    "shipments_count": n,
                    "total_cargo_tons": total_tons,
                    "avg_haversine_km": avg_hav_km,
                    "avg_road_distance_km": avg_road_km,
                    "avg_promised_sla_hours": avg_promised_h,
                    "avg_actual_delivery_hours": avg_actual_h,
                    "avg_dock_dwell_hours": avg_dock_h,
                    "avg_effective_speed_kmh": avg_speed_kmh,
                    "sla_breach_rate_pct": sla_breach_pct,
                    "corridor_bottleneck_index": corridor_lbi,
                    "bottleneck_severity": severity,
                    "primary_bottleneck_cause": primary_cause,
                    "geom_corridor_wkt": make_wkt_linestring(o_lon, o_lat, d_lon, d_lat),
                }
            )

        corridors.sort(key=lambda c: c["corridor_bottleneck_index"], reverse=True)
        return corridors
