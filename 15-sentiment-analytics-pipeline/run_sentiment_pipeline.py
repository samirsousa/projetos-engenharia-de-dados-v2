"""
Orquestrador End-to-End do Projeto 15: Social Media Sentiment & Engagement Analytics Pipeline.

Executa sequencialmente:
1. Geração e leitura do arquivo JSON contendo avaliações de clientes e menções sociais (`customer_social_reviews.json`).
2. Limpeza textual (remoção de HTML, URLs, menções, stopwords PT-BR) e aplicação do Dicionário Léxico de
   Polaridade PT-BR com janela contextual de negação ("não é bom") e intensificadores ("extremamente rápido").
3. Consolidação das métricas de satisfação (NPS simulado, proporção de sentimentos positivos/neutros/negativos
   por categoria de produto e engajamento ponderado) em um Star Schema Dimensional no SQLite (`sentiment_analytics_dw.db`).
4. Exportação do modelo pronto para dashboard analítico (CSV + Apache Parquet) e Relatório Executivo Markdown.
"""

from __future__ import annotations

import argparse
import shutil
import time
from typing import Dict, Any

from src.config import (
    DASHBOARD_MART_DIR,
    DATA_DIR,
    RAW_REVIEWS_JSON_PATH,
    REPORTS_DIR,
    SQLITE_DB_PATH,
    ensure_directories,
)
from src.dimensional_builder import (
    DimensionalSentimentBuilder,
    export_dashboard_marts_and_report,
)
from src.review_generator import save_reviews_json
from src.sentiment_engine import SentimentAnalyticsProcessor


def run_sentiment_pipeline(
    clean: bool = False,
    seed: int = 42,
    total_reviews: int = 1250,
) -> Dict[str, Any]:
    start_ts = time.perf_counter()

    if clean:
        for d in (DATA_DIR, REPORTS_DIR):
            if d.exists():
                shutil.rmtree(d)

    ensure_directories()

    print("=" * 86)
    print("  PROJETO 15: SOCIAL MEDIA SENTIMENT, ENGAGEMENT & NPS ANALYTICS PIPELINE (PT-BR)")
    print("=" * 86)

    # 1. Geração/Ingestão do JSON de Avaliações
    print("\n[1/4] Gerando e lendo arquivo JSON de avaliações de clientes (`customer_social_reviews.json`)...")
    json_meta = save_reviews_json(
        total_reviews=total_reviews, seed=seed, output_path=RAW_REVIEWS_JSON_PATH
    )
    print(f"      - Arquivo JSON processado: {json_meta['json_path']}")
    print(f"      - Avaliações extraídas   : {json_meta['total_reviews']:,}")

    # 2. Limpeza Textual e Motor de Polaridade Léxica PT-BR
    print("\n[2/4] Aplicando limpeza de texto e dicionário de polaridade PT-BR (Negação + Intensidade)...")
    processor = SentimentAnalyticsProcessor()
    enriched_reviews = processor.process_json_file(RAW_REVIEWS_JSON_PATH)
    print(f"      - Avaliações enriquecidas com sentimento e engajamento: {len(enriched_reviews):,}")

    # 3. Construção do Modelo Dimensional (Star Schema) e Cálculo de NPS por Categoria
    print("\n[3/4] Consolidando Star Schema Dimensional e métricas de NPS por categoria no SQLite...")
    builder = DimensionalSentimentBuilder(db_path=SQLITE_DB_PATH)
    build_results = builder.build_and_persist(enriched_reviews)
    for tbl, cnt in build_results["table_counts"].items():
        print(f"      - {tbl:<38}: {cnt:>5,} linhas")

    # 4. Exportação para Dashboard Analítico (CSV + Parquet) e Relatório Executivo
    print("\n[4/4] Exportando tabelas do modelo para Dashboard (CSV + Parquet) e Relatório...")
    exported = export_dashboard_marts_and_report(
        build_results, mart_dir=DASHBOARD_MART_DIR
    )

    elapsed = time.perf_counter() - start_ts
    k = build_results["global_kpis"]

    print("\n" + "=" * 86)
    print("  RESUMO EXECUTIVO DE SATISFAÇÃO (NPS), SENTIMENTO E ENGAJAMENTO SOCIAL")
    print("=" * 86)
    print(f"  * Total de Avaliações Analisadas      : {k['total_reviews']:,}")
    print(f"  * Sentimentos Positivos               : {k['positive_count']:,} ({k['positive_ratio_pct']:.2f}%)")
    print(f"  * Sentimentos Neutros                 : {k['neutral_count']:,} ({k['neutral_ratio_pct']:.2f}%)")
    print(f"  * Sentimentos Negativos               : {k['negative_count']:,} ({k['negative_ratio_pct']:.2f}%)")
    print("-" * 86)
    print(f"  * Promotores / Neutros / Detratores   : {k['promoters_count']} / {k['passives_count']} / {k['detractors_count']}")
    print(f"  * NPS Simulado Global                 : {k['global_simulated_nps']:+.2f} pts")
    print(f"  * Polaridade Composta Média [-1, +1]  : {k['avg_compound_polarity']:+.4f}")
    print(f"  * Frases com Negação Invertida ('não'): {k['negation_handled_reviews']:,}")
    print("-" * 86)
    print(f"  * Alcance Total (Impressões)          : {k['total_impressions']:,}")
    print(f"  * Total de Interações Sociais         : {k['total_interactions']:,} (Taxa Média: {k['avg_engagement_rate_pct']:.2f}%)")
    print("-" * 86)
    print(f"  * Banco Dimensional SQLite            : {SQLITE_DB_PATH}")
    print(f"  * Diretório Dashboard Mart (CSV/Parq.): {DASHBOARD_MART_DIR}")
    print(f"  * Relatório Executivo Markdown        : {exported['executive_markdown_report']}")
    print("=" * 86)
    print(f"Pipeline concluído com sucesso em {elapsed:.2f}s.\n")

    return {
        "json_meta": json_meta,
        "table_counts": build_results["table_counts"],
        "global_kpis": k,
        "exported": exported,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa o pipeline de análise de sentimento PT-BR, NPS e engajamento social."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove artefatos anteriores antes de executar o pipeline.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed aleatória para reprodutibilidade determinística (padrão: 42).",
    )
    args = parser.parse_args()
    run_sentiment_pipeline(clean=args.clean, seed=args.seed)


if __name__ == "__main__":
    main()
