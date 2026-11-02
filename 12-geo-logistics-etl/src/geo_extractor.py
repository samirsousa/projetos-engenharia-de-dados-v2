"""
Módulo de Extração e Geração Sintética de Telemetria Geoespacial e Remessas Logísticas (Stage 1 - Extract).

Simula eventos operacionais de transporte rodoviário/rodofluvial de cargas no Brasil:
- Coordenadas GPS WGS-84 de Origem (Hubs Logísticos) e Destino (Endereços Last-Mile em 14 polos).
- Pesos de carga (kg e toneladas), cubagem (m³), valor de nota fiscal (R$) e modal veicular.
- Prazos contratados (SLA Promised Hours) vs. Tempos Reais de Trânsito e Doca.
- Injeção controlada de anomalias geoespaciais reais de telemetria GPS:
  1. Coordenadas invertidas (Lat/Lon trocados — recuperáveis por Auto-Healing).
  2. Coordenadas "Null Island" (0.0, 0.0) ou fora do território nacional (enviadas para Quarentena).
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple

from src.config import (
    DESTINATION_POLES,
    EARTH_RADIUS_KM,
    LOGISTICS_HUBS,
    RAW_TELEMETRY_DIR,
    VEHICLE_MODALS,
    ensure_directories,
)

CARGO_CATEGORIES = [
    "Eletrônicos & Semicondutores",
    "Bens de Consumo & Varejo (FMCG)",
    "Fármacos & Termolábeis",
    "Autopeças & Componentes Industriais",
    "Insumos Agrícolas & Embalagens",
]

BOTTLENECK_CAUSES = [
    ("Normal Flow", 0.58),
    ("Urban Ring-Road Congestion (Marginal / Av. Brasil)", 0.16),
    ("Port / Fiscal Barrier Inspection (SEFAZ Posto Fiscal)", 0.10),
    ("Dock Queue Overload at Origin/Destination", 0.08),
    ("Severe Weather / Serra Highway Speed Restriction", 0.05),
    ("Ferry / Rodofluvial Barge Wait Time", 0.03),
]


def _quick_haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Cálculo rápido de Haversine para parametrizar o SLA contratado realista na geração."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def _weighted_choice(rng: random.Random, items: List[Tuple[Any, float]]) -> Any:
    total = sum(w for _, w in items)
    r = rng.uniform(0.0, total)
    acc = 0.0
    for val, weight in items:
        if acc + weight >= r:
            return val
        acc += weight
    return items[-1][0]


class GeospatialLogisticsExtractor:
    """Gerador e extrator de lotes brutos de telemetria GPS e manifesto eletrônico de cargas (MDF-e)."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_raw_batches(
        self, total_shipments: int = 960
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Gera os arquivos brutos de Hubs Logísticos (`raw_hubs`) e Remessas de Transporte (`raw_shipments`),
        incluindo casos reais de gargalo logístico e anomalias de telemetria GPS para validação do ETL.
        """
        hubs_by_region: Dict[str, List[Dict[str, Any]]] = {}
        for h in LOGISTICS_HUBS:
            hubs_by_region.setdefault(h["macro_region"], []).append(h)

        dest_weights = [(pole, pole["weight"]) for pole in DESTINATION_POLES]
        cause_weights = BOTTLENECK_CAUSES

        shipments: List[Dict[str, Any]] = []
        base_dt = datetime(2026, 1, 1, 6, 0, 0)

        for seq in range(1, total_shipments + 1):
            shipment_id = f"SHP-{seq:05d}"
            dest_pole = _weighted_choice(self.rng, dest_weights)

            # Seleção de Hub de Origem: 65% de chance de sair do Hub mais próximo/regional,
            # 35% de transferência nacional (Long-Haul Cross-Docking a partir de SP/MG)
            if dest_pole["macro_region"] in hubs_by_region and self.rng.random() < 0.62:
                origin_hub = self.rng.choice(hubs_by_region[dest_pole["macro_region"]])
            else:
                origin_hub = _weighted_choice(
                    self.rng,
                    [
                        (LOGISTICS_HUBS[0], 0.42),  # Cajamar SP
                        (LOGISTICS_HUBS[1], 0.25),  # Extrema MG
                        (LOGISTICS_HUBS[2], 0.14),  # Araucária PR
                        (LOGISTICS_HUBS[3], 0.10),  # Cabo PE
                        (LOGISTICS_HUBS[4], 0.09),  # Anápolis GO
                    ],
                )

            # Dispersão espacial Last-Mile ao redor do centroide do polo consumidor (~8 a 35 km)
            lat_jitter = self.rng.gauss(0.0, 0.085)
            lon_jitter = self.rng.gauss(0.0, 0.085)
            dest_lat = round(dest_pole["lat"] + lat_jitter, 6)
            dest_lon = round(dest_pole["lon"] + lon_jitter, 6)

            origin_lat = round(origin_hub["latitude"] + self.rng.gauss(0.0, 0.004), 6)
            origin_lon = round(origin_hub["longitude"] + self.rng.gauss(0.0, 0.004), 6)

            dist_hav = _quick_haversine_km(origin_lat, origin_lon, dest_lat, dest_lon)
            est_road_km = dist_hav * dest_pole["road_circuity"]

            # Escolha do modal conforme distância do corredor
            if est_road_km < 120.0:
                modal_key = self.rng.choices(
                    ["VUC_URBANO", "TOCO_SEMIPESADO", "CARRETA_SIDER"],
                    weights=[0.55, 0.35, 0.10],
                )[0]
            elif est_road_km < 650.0:
                modal_key = self.rng.choices(
                    ["VUC_URBANO", "TOCO_SEMIPESADO", "CARRETA_SIDER", "BITREM_RODOTREM"],
                    weights=[0.10, 0.42, 0.36, 0.12],
                )[0]
            else:
                modal_key = self.rng.choices(
                    ["TOCO_SEMIPESADO", "CARRETA_SIDER", "BITREM_RODOTREM"],
                    weights=[0.18, 0.52, 0.30],
                )[0]

            modal_meta = VEHICLE_MODALS[modal_key]
            # Fator de ocupação da capacidade do veículo (42% a 96%)
            load_factor = self.rng.uniform(0.42, 0.96)
            cargo_weight_kg = round(modal_meta["max_weight_kg"] * load_factor, 2)
            cargo_volume_m3 = round(cargo_weight_kg / self.rng.uniform(180.0, 340.0), 2)
            cargo_category = self.rng.choice(CARGO_CATEGORIES)
            cargo_value_brl = round(cargo_weight_kg * self.rng.uniform(8.5, 42.0), 2)

            # Cálculo do SLA Prometido (Horas) = Tempo de Doca Padrão + Trânsito Rodoviário + Descarga/ descansos legais
            cruise_hours = est_road_km / modal_meta["avg_cruise_speed_kmh"]
            mandatory_rest_hours = math.floor(cruise_hours / 5.5) * 1.5
            promised_sla_hours = round(
                max(4.0, origin_hub["avg_dock_dwell_hours"] + cruise_hours + mandatory_rest_hours + 3.0),
                2,
            )

            # Simulação de Gargalos Logísticos Reais (Doca + Trânsito + Barreira Fiscal)
            dock_dwell_hours = round(
                origin_hub["avg_dock_dwell_hours"] * self.rng.uniform(0.75, 1.85), 2
            )
            is_congested = self.rng.random() < dest_pole["structural_congestion"]
            if is_congested:
                delay_factor = self.rng.uniform(1.18, 1.72)
                bottleneck_cause = _weighted_choice(self.rng, cause_weights[1:])
                dock_dwell_hours = round(dock_dwell_hours + self.rng.uniform(1.2, 4.8), 2)
            else:
                delay_factor = self.rng.uniform(0.82, 1.06)
                bottleneck_cause = "Normal Flow"

            actual_transit_hours = round(
                dock_dwell_hours + (cruise_hours * delay_factor) + mandatory_rest_hours,
                2,
            )

            dispatch_dt = base_dt + timedelta(
                days=self.rng.randint(0, 89),
                hours=self.rng.randint(0, 23),
                minutes=self.rng.randint(0, 59),
            )
            promised_dt = dispatch_dt + timedelta(hours=promised_sla_hours)
            actual_dt = dispatch_dt + timedelta(hours=actual_transit_hours)

            # Injeção controlada de anomalias de qualidade geoespacial para demonstrar resiliência do ETL:
            # - 8 registros com Lat/Lon invertidos (Swapped Coordinates -> Auto-Healed no Transform)
            # - 6 registros com coordenadas Null Island (0.0, 0.0) ou fora do globo -> Quarentenados
            if seq in (105, 210, 315, 420, 525, 630, 735, 840):
                # Swapped coordinates (Lon colocado no lugar de Lat e vice-versa)
                dest_lat, dest_lon = dest_lon, dest_lat
            elif seq in (99, 299, 499, 699, 899, 950):
                # Coordenada corrompida (Null Island / GPS sem sinal)
                dest_lat, dest_lon = 0.0, 0.0

            shipments.append(
                {
                    "shipment_id": shipment_id,
                    "origin_hub_id": origin_hub["hub_id"],
                    "origin_city": origin_hub["city"],
                    "origin_uf": origin_hub["state_uf"],
                    "origin_macro_region": origin_hub["macro_region"],
                    "origin_latitude": origin_lat,
                    "origin_longitude": origin_lon,
                    "dest_zone_id": dest_pole["zone_id"],
                    "dest_city": dest_pole["city"],
                    "dest_uf": dest_pole["state_uf"],
                    "dest_macro_region": dest_pole["macro_region"],
                    "dest_zone_area_km2": dest_pole["area_km2"],
                    "road_circuity_factor": dest_pole["road_circuity"],
                    "dest_latitude": dest_lat,
                    "dest_longitude": dest_lon,
                    "vehicle_modal": modal_key,
                    "cargo_category": cargo_category,
                    "cargo_weight_kg": cargo_weight_kg,
                    "cargo_volume_m3": cargo_volume_m3,
                    "cargo_value_brl": cargo_value_brl,
                    "dispatch_timestamp": dispatch_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "promised_delivery_timestamp": promised_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "actual_delivery_timestamp": actual_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "promised_sla_hours": promised_sla_hours,
                    "actual_delivery_hours": actual_transit_hours,
                    "origin_dock_dwell_hours": dock_dwell_hours,
                    "reported_bottleneck_cause": bottleneck_cause,
                }
            )

        return {
            "raw_hubs": LOGISTICS_HUBS,
            "raw_shipments": shipments,
        }


def save_raw_telemetry_csvs(
    batches: Dict[str, List[Dict[str, Any]]],
    output_dir: Path = RAW_TELEMETRY_DIR,
) -> Dict[str, Path]:
    """Persiste os lotes brutos extraídos em arquivos CSV na camada raw_telemetry."""
    ensure_directories()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, Path] = {}

    for name, rows in batches.items():
        if not rows:
            continue
        csv_path = output_dir / f"{name}.csv"
        fieldnames = list(rows[0].keys())
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        paths[name] = csv_path

    return paths
