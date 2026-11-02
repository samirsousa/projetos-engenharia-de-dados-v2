"""
Configurações centrais do Projeto 12: ETL de Dados Geoespaciais e Logísticos.
Define diretórios, constantes geodésicas (Raio médio da Terra WGS-84, Bounding Box do Brasil),
Centros de Distribuição (Hubs), zonas de entrega, fatores de tortuosidade rodoviária e modais.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_TELEMETRY_DIR = DATA_DIR / "raw_telemetry"
SILVER_ENRICHED_DIR = DATA_DIR / "silver_enriched"
GOLD_WAREHOUSE_DIR = DATA_DIR / "gold_warehouse"
MAP_EXPORTS_DIR = DATA_DIR / "map_exports"
REPORTS_DIR = PROJECT_ROOT / "reports"

SQLITE_DB_PATH = GOLD_WAREHOUSE_DIR / "geo_logistics_dw.db"

# Constantes Geodésicas (Elipsoide WGS-84 / Raio Médio Esférico IUGG)
EARTH_RADIUS_KM: float = 6371.0088

# Bounding Box Oficial do Território Brasileiro (para validação de coordenadas GPS)
BRAZIL_BBOX = {
    "min_lat": -33.75,  # Arroio Chuí (RS)
    "max_lat": 5.27,    # Monte Caburaí (RR)
    "min_lon": -73.99,  # Serra do Divisor (AC)
    "max_lon": -34.79,  # Ponta do Seixas (PB)
}

# Centros de Distribuição (CDs / Origens Logísticas)
LOGISTICS_HUBS: List[Dict[str, Any]] = [
    {
        "hub_id": "HUB-SP-CAJ",
        "hub_name": "CD Cajamar MegaHub (SP)",
        "city": "Cajamar",
        "state_uf": "SP",
        "macro_region": "Sudeste",
        "latitude": -23.3556,
        "longitude": -46.8769,
        "dock_capacity_tons_day": 480.0,
        "avg_dock_dwell_hours": 2.4,
    },
    {
        "hub_id": "HUB-MG-EXT",
        "hub_name": "CD Extrema Sul de Minas (MG)",
        "city": "Extrema",
        "state_uf": "MG",
        "macro_region": "Sudeste",
        "latitude": -22.8547,
        "longitude": -46.3183,
        "dock_capacity_tons_day": 350.0,
        "avg_dock_dwell_hours": 2.8,
    },
    {
        "hub_id": "HUB-PR-CWB",
        "hub_name": "CD Curitiba Araucária (PR)",
        "city": "Araucária",
        "state_uf": "PR",
        "macro_region": "Sul",
        "latitude": -25.5858,
        "longitude": -49.4047,
        "dock_capacity_tons_day": 290.0,
        "avg_dock_dwell_hours": 2.1,
    },
    {
        "hub_id": "HUB-PE-REC",
        "hub_name": "CD Cabo de Santo Agostinho (PE)",
        "city": "Cabo de Santo Agostinho",
        "state_uf": "PE",
        "macro_region": "Nordeste",
        "latitude": -8.2833,
        "longitude": -35.0333,
        "dock_capacity_tons_day": 260.0,
        "avg_dock_dwell_hours": 3.9,
    },
    {
        "hub_id": "HUB-GO-ANP",
        "hub_name": "CD Porto Seco Anápolis (GO)",
        "city": "Anápolis",
        "state_uf": "GO",
        "macro_region": "Centro-Oeste",
        "latitude": -16.3281,
        "longitude": -48.9531,
        "dock_capacity_tons_day": 240.0,
        "avg_dock_dwell_hours": 3.2,
    },
]

# Polos Consumidores e Zonas de Entrega (Destinos com área territorial aproximada da malha metropolitana em km²)
DESTINATION_POLES: List[Dict[str, Any]] = [
    {"zone_id": "ZN-SP-CAP", "city": "São Paulo", "state_uf": "SP", "macro_region": "Sudeste", "lat": -23.5505, "lon": -46.6333, "area_km2": 1521.0, "road_circuity": 1.24, "structural_congestion": 0.35, "weight": 0.16},
    {"zone_id": "ZN-RJ-CAP", "city": "Rio de Janeiro", "state_uf": "RJ", "macro_region": "Sudeste", "lat": -22.9068, "lon": -43.1729, "area_km2": 1200.0, "road_circuity": 1.29, "structural_congestion": 0.42, "weight": 0.11},
    {"zone_id": "ZN-MG-BHZ", "city": "Belo Horizonte", "state_uf": "MG", "macro_region": "Sudeste", "lat": -19.9167, "lon": -43.9345, "area_km2": 950.0, "road_circuity": 1.31, "structural_congestion": 0.28, "weight": 0.09},
    {"zone_id": "ZN-SP-CPS", "city": "Campinas", "state_uf": "SP", "macro_region": "Sudeste", "lat": -22.9099, "lon": -47.0626, "area_km2": 795.0, "road_circuity": 1.18, "structural_congestion": 0.15, "weight": 0.08},
    {"zone_id": "ZN-PR-CWB", "city": "Curitiba", "state_uf": "PR", "macro_region": "Sul", "lat": -25.4284, "lon": -49.2733, "area_km2": 850.0, "road_circuity": 1.21, "structural_congestion": 0.18, "weight": 0.07},
    {"zone_id": "ZN-RS-POA", "city": "Porto Alegre", "state_uf": "RS", "macro_region": "Sul", "lat": -30.0346, "lon": -51.2177, "area_km2": 1100.0, "road_circuity": 1.27, "structural_congestion": 0.25, "weight": 0.07},
    {"zone_id": "ZN-SC-FLN", "city": "Florianópolis / Itajaí", "state_uf": "SC", "macro_region": "Sul", "lat": -27.5954, "lon": -48.5480, "area_km2": 920.0, "road_circuity": 1.26, "structural_congestion": 0.31, "weight": 0.06},
    {"zone_id": "ZN-BA-SSA", "city": "Salvador", "state_uf": "BA", "macro_region": "Nordeste", "lat": -12.9714, "lon": -38.5014, "area_km2": 1050.0, "road_circuity": 1.34, "structural_congestion": 0.38, "weight": 0.07},
    {"zone_id": "ZN-PE-REC", "city": "Recife", "state_uf": "PE", "macro_region": "Nordeste", "lat": -8.0476, "lon": -34.8770, "area_km2": 880.0, "road_circuity": 1.28, "structural_congestion": 0.36, "weight": 0.06},
    {"zone_id": "ZN-CE-FOR", "city": "Fortaleza", "state_uf": "CE", "macro_region": "Nordeste", "lat": -3.7172, "lon": -38.5433, "area_km2": 960.0, "road_circuity": 1.32, "structural_congestion": 0.33, "weight": 0.06},
    {"zone_id": "ZN-DF-BSB", "city": "Brasília", "state_uf": "DF", "macro_region": "Centro-Oeste", "lat": -15.7975, "lon": -47.8919, "area_km2": 1350.0, "road_circuity": 1.19, "structural_congestion": 0.16, "weight": 0.06},
    {"zone_id": "ZN-MT-CGB", "city": "Cuiabá", "state_uf": "MT", "macro_region": "Centro-Oeste", "lat": -15.6014, "lon": -56.0979, "area_km2": 1400.0, "road_circuity": 1.36, "structural_congestion": 0.44, "weight": 0.04},
    {"zone_id": "ZN-PA-BEL", "city": "Belém", "state_uf": "PA", "macro_region": "Norte", "lat": -1.4558, "lon": -48.4902, "area_km2": 1250.0, "road_circuity": 1.44, "structural_congestion": 0.56, "weight": 0.04},
    {"zone_id": "ZN-AM-MAO", "city": "Manaus (Rodofluvial)", "state_uf": "AM", "macro_region": "Norte", "lat": -3.1190, "lon": -60.0217, "area_km2": 1800.0, "road_circuity": 1.52, "structural_congestion": 0.64, "weight": 0.03},
]

VEHICLE_MODALS: Dict[str, Dict[str, Any]] = {
    "VUC_URBANO": {
        "modal_name": "VUC Urbano (3.5t)",
        "max_weight_kg": 3500.0,
        "avg_cruise_speed_kmh": 42.0,
        "cost_per_t_km_brl": 1.48,
        "co2_kg_per_t_km": 0.115,
    },
    "TOCO_SEMIPESADO": {
        "modal_name": "Caminhão Toco 2 Eixos (12t)",
        "max_weight_kg": 12000.0,
        "avg_cruise_speed_kmh": 58.0,
        "cost_per_t_km_brl": 0.68,
        "co2_kg_per_t_km": 0.074,
    },
    "CARRETA_SIDER": {
        "modal_name": "Carreta Sider 3 Eixos (28t)",
        "max_weight_kg": 28000.0,
        "avg_cruise_speed_kmh": 62.0,
        "cost_per_t_km_brl": 0.44,
        "co2_kg_per_t_km": 0.052,
    },
    "BITREM_RODOTREM": {
        "modal_name": "Bitrem Alta Capacidade (45t)",
        "max_weight_kg": 45000.0,
        "avg_cruise_speed_kmh": 56.0,
        "cost_per_t_km_brl": 0.36,
        "co2_kg_per_t_km": 0.041,
    },
}


def ensure_directories() -> None:
    """Garante a existência de todos os diretórios de dados e relatórios."""
    for d in (
        RAW_TELEMETRY_DIR,
        SILVER_ENRICHED_DIR,
        GOLD_WAREHOUSE_DIR,
        MAP_EXPORTS_DIR,
        REPORTS_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
