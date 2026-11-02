"""
Suíte de Testes Automatizados do Projeto 12: ETL de Dados Geoespaciais e Logísticos.

Valida:
1. Precisão matemática das funções geodésicas (Haversine, Azimute, Geohash-6 e WKT).
2. Auto-Healing de coordenadas invertidas (Lat/Lon Swap) e Quarentena de coordenadas inválidas.
3. Cálculo de Densidade Regional de Entregas e Índice de Gargalo Logístico (LBI).
4. Persistência relacional no SQLite (tabelas e Views para mapas gerenciais) e exportação GeoJSON RFC 7946.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.geo_extractor import GeospatialLogisticsExtractor, save_raw_telemetry_csvs
from src.geo_loader import (
    export_map_layers_and_geojson,
    generate_geospatial_executive_report,
    load_to_sqlite_warehouse,
)
from src.geo_transformer import (
    GeospatialLogisticsTransformer,
    azimuth_to_cardinal,
    encode_geohash,
    forward_azimuth_degrees,
    haversine_distance_km,
    make_wkt_linestring,
    make_wkt_point,
    validate_and_heal_coordinates,
)


class TestGeoLogisticsETL(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.base_path = Path(cls.temp_dir.name)
        cls.raw_dir = cls.base_path / "raw_telemetry"
        cls.silver_dir = cls.base_path / "silver_enriched"
        cls.map_dir = cls.base_path / "map_exports"
        cls.db_path = cls.base_path / "gold_warehouse" / "test_geo_dw.db"
        cls.report_path = cls.base_path / "reports" / "geo_report.md"

        extractor = GeospatialLogisticsExtractor(seed=42)
        cls.raw_batches = extractor.generate_raw_batches(total_shipments=240)
        save_raw_telemetry_csvs(cls.raw_batches, output_dir=cls.raw_dir)

        transformer = GeospatialLogisticsTransformer()
        cls.transformed = transformer.transform(
            cls.raw_batches["raw_hubs"], cls.raw_batches["raw_shipments"]
        )
        cls.db_counts = load_to_sqlite_warehouse(cls.transformed, db_path=cls.db_path)
        cls.exported = export_map_layers_and_geojson(
            cls.transformed,
            db_path=cls.db_path,
            silver_dir=cls.silver_dir,
            map_dir=cls.map_dir,
        )
        cls.report_file, cls.kpis = generate_geospatial_executive_report(
            cls.transformed, report_path=cls.report_path
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_01_geodesic_math_and_geohash_accuracy(self) -> None:
        """Valida distância de Haversine (SP -> RJ ~357 km), Azimute, Geohash e WKT."""
        # São Paulo (-23.5505, -46.6333) -> Rio de Janeiro (-22.9068, -43.1729)
        dist_sp_rj = haversine_distance_km(-23.5505, -46.6333, -22.9068, -43.1729)
        self.assertGreater(dist_sp_rj, 350.0)
        self.assertLess(dist_sp_rj, 365.0)

        azimuth = forward_azimuth_degrees(-23.5505, -46.6333, -22.9068, -43.1729)
        self.assertGreater(azimuth, 65.0)
        self.assertLess(azimuth, 85.0)
        self.assertIn(azimuth_to_cardinal(azimuth), ("E", "NE"))

        gh = encode_geohash(-23.5505, -46.6333, precision=6)
        self.assertEqual(len(gh), 6)
        self.assertEqual(gh, "6gyf4b")

        self.assertEqual(make_wkt_point(-46.6333, -23.5505), "POINT (-46.633300 -23.550500)")
        self.assertTrue(
            make_wkt_linestring(-46.6333, -23.5505, -43.1729, -22.9068).startswith("LINESTRING (")
        )

    def test_02_coordinate_auto_healing_and_quarantine(self) -> None:
        """Verifica se coordenadas invertidas (Lat/Lon Swap) são curadas e (0,0) vai para quarentena."""
        # Coordenada válida original em SP
        ok, lat, lon, status = validate_and_heal_coordinates(-23.5505, -46.6333)
        self.assertTrue(ok)
        self.assertEqual(status, "VALID_ORIGINAL")

        # Coordenada invertida (-46.6333 no lugar de lat, -23.5505 no lugar de lon)
        ok_swap, h_lat, h_lon, status_swap = validate_and_heal_coordinates(-46.6333, -23.5505)
        self.assertTrue(ok_swap)
        self.assertEqual(h_lat, -23.5505)
        self.assertEqual(h_lon, -46.6333)
        self.assertEqual(status_swap, "AUTO_HEALED_SWAPPED_LATLON")

        # Coordenada Null Island (0.0, 0.0)
        ok_null, _, _, status_null = validate_and_heal_coordinates(0.0, 0.0)
        self.assertFalse(ok_null)
        self.assertEqual(status_null, "QUARANTINED_NULL_ISLAND_ZERO_COORD")

        # Verifica reconciliação entre total bruto = válidos + quarentenados
        self.assertEqual(
            len(self.raw_batches["raw_shipments"]),
            len(self.transformed["fact_shipments_geospatial"])
            + len(self.transformed["quarantine_spatial_anomalies"]),
        )
        self.assertGreater(self.kpis["auto_healed_swapped_coords"], 0)
        self.assertGreater(self.kpis["total_quarantined_anomalies"], 0)

    def test_03_regional_density_and_bottleneck_metrics(self) -> None:
        """Garante que a densidade de entregas por 1.000 km² e os gargalos de corredor sejam válidos."""
        density_rows = self.transformed["mart_regional_delivery_density"]
        corridor_rows = self.transformed["mart_corridor_bottlenecks"]

        self.assertEqual(len(density_rows), 14)
        self.assertGreater(len(corridor_rows), 15)

        for r in density_rows:
            self.assertGreater(r["delivery_density_shipments_per_1000km2"], 0.0)
            self.assertGreater(r["cargo_density_tons_per_km2"], 0.0)
            self.assertAlmostEqual(r["otif_rate_pct"] + r["sla_breach_rate_pct"], 100.0, places=1)

        # Verifica ordenação decrescente do índice de gargalo nos corredores
        scores = [c["corridor_bottleneck_index"] for c in corridor_rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_04_sqlite_warehouse_and_geojson_map_export(self) -> None:
        """Valida se o banco SQLite, as Views de mapas e o GeoJSON RFC 7946 foram persistidos."""
        self.assertTrue(self.db_path.exists())
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM vw_map_flow_arcs")
            flow_count = cur.fetchone()[0]
            self.assertEqual(flow_count, len(self.transformed["mart_corridor_bottlenecks"]))

            cur.execute("SELECT COUNT(*) FROM vw_map_heatmap_grid_cells")
            grid_count = cur.fetchone()[0]
            self.assertGreater(grid_count, 0)
        finally:
            conn.close()

        geojson_path = Path(self.exported["geojson_map"])
        self.assertTrue(geojson_path.exists())
        payload = json.loads(geojson_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertGreater(len(payload["features"]), 20)
        self.assertTrue(self.report_file.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
