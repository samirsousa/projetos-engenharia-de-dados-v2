"""
Suíte de Testes Automatizados do Projeto 15: Social Media Sentiment & Engagement Analytics Pipeline.

Valida:
1. Limpeza textual PT-BR (remoção de HTML, URLs, menções, extração de hashtags e preservação de negações).
2. Motor de Sentimento Baseado em Léxico PT-BR (inversão por negação "não é bom" e intensificadores).
3. Consolidação de NPS Simulado e proporção de sentimentos por categoria no Star Schema SQLite.
4. Exportação das tabelas do modelo para Dashboard Analítico (CSV, Parquet e Relatório Markdown).
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.dimensional_builder import (
    DimensionalSentimentBuilder,
    export_dashboard_marts_and_report,
)
from src.review_generator import save_reviews_json
from src.sentiment_engine import (
    SentimentAnalyticsProcessor,
    clean_and_normalize_text_ptbr,
    score_sentiment_ptbr,
)


class TestSentimentAnalyticsPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.base_path = Path(cls.temp_dir.name)
        cls.json_path = cls.base_path / "raw_json" / "test_reviews.json"
        cls.db_path = cls.base_path / "warehouse" / "test_sentiment_dw.db"
        cls.mart_dir = cls.base_path / "dashboard_mart"
        cls.report_path = cls.base_path / "reports" / "executive_report.md"

        cls.json_meta = save_reviews_json(
            total_reviews=300, seed=42, output_path=cls.json_path
        )
        processor = SentimentAnalyticsProcessor()
        cls.enriched = processor.process_json_file(cls.json_path)

        builder = DimensionalSentimentBuilder(db_path=cls.db_path)
        cls.build_res = builder.build_and_persist(cls.enriched)
        cls.exported = export_dashboard_marts_and_report(
            cls.build_res, mart_dir=cls.mart_dir, report_path=cls.report_path
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_01_text_cleaning_and_tokenization_ptbr(self) -> None:
        """Verifica se HTML, URLs e menções são limpos e se negações/intensificadores são mantidos."""
        raw = "Não é bom! <br/> Muito lento @LojaTeste https://exemplo.com/item #Decepcao #Arrependido"
        cleaned = clean_and_normalize_text_ptbr(raw)

        self.assertNotIn("<br/>", cleaned["cleaned_text"])
        self.assertNotIn("https://", cleaned["cleaned_text"])
        self.assertEqual(cleaned["hashtags"], ["decepcao", "arrependido"])
        self.assertEqual(cleaned["mentions"], ["lojateste"])
        self.assertIn("nao", cleaned["tokens"])
        self.assertIn("muito", cleaned["tokens"])
        self.assertIn("bom", cleaned["tokens"])

    def test_02_ptbr_lexicon_polarity_and_negation_inversion(self) -> None:
        """
        Valida o dicionário de polaridade PT-BR:
        - Frase positiva -> POSITIVE / PROMOTER
        - Frase com negação ("Não é bom, não recomendo") -> Inversão para NEGATIVE / DETRACTOR
        - Frase neutra -> NEUTRAL / PASSIVE
        """
        pos_clean = clean_and_normalize_text_ptbr(
            "Produto muito excelente, super rápido e impecável! Recomendo demais!"
        )
        pos_score = score_sentiment_ptbr(pos_clean["tokens"], pos_clean["hashtags"])
        self.assertEqual(pos_score["sentiment_label"], "POSITIVE")
        self.assertEqual(pos_score["nps_segment"], "PROMOTER")
        self.assertGreater(pos_score["compound_sentiment_score"], 0.60)

        negated_clean = clean_and_normalize_text_ptbr(
            "Não é bom e não recomendo para ninguém!"
        )
        negated_score = score_sentiment_ptbr(
            negated_clean["tokens"], negated_clean["hashtags"]
        )
        self.assertEqual(negated_score["negation_detected_flag"], 1)
        self.assertEqual(negated_score["sentiment_label"], "NEGATIVE")
        self.assertEqual(negated_score["nps_segment"], "DETRACTOR")
        self.assertLess(negated_score["compound_sentiment_score"], -0.25)

        neu_clean = clean_and_normalize_text_ptbr(
            "Produto básico, normal e comum para o cotidiano."
        )
        neu_score = score_sentiment_ptbr(neu_clean["tokens"], neu_clean["hashtags"])
        self.assertEqual(neu_score["sentiment_label"], "NEUTRAL")
        self.assertEqual(neu_score["nps_segment"], "PASSIVE")

    def test_03_dimensional_star_schema_and_category_nps(self) -> None:
        """
        Verifica se as tabelas dimensionais e `mart_category_satisfaction_nps`
        foram persistidas corretamente no SQLite e respeitam as identidades matemáticas.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM mart_category_satisfaction_nps")
            cat_rows = [dict(r) for r in cur.fetchall()]
            self.assertEqual(len(cat_rows), 5)

            total_cat_reviews = sum(r["total_reviews"] for r in cat_rows)
            self.assertEqual(total_cat_reviews, 300)

            for r in cat_rows:
                # Soma das proporções Positivo + Neutro + Negativo deve ser ~100%
                self.assertAlmostEqual(
                    r["positive_ratio_pct"] + r["neutral_ratio_pct"] + r["negative_ratio_pct"],
                    100.0,
                    places=1,
                )
                # NPS = % Promotores - % Detratores
                self.assertAlmostEqual(
                    r["simulated_nps_score"],
                    r["promoters_pct"] - r["detractors_pct"],
                    places=1,
                )
        finally:
            conn.close()

    def test_04_dashboard_exports_csv_parquet_and_report(self) -> None:
        """Confirma que todos os arquivos CSV, Parquet e o relatório Markdown foram exportados."""
        self.assertTrue(self.report_path.exists())
        for key, path_str in self.exported.items():
            self.assertTrue(Path(path_str).exists(), f"Artefato ausente: {key}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
