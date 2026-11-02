"""
Motor de Limpeza Textual e Análise de Sentimento Baseada em Léxico/Regras PT-BR (Stage 2).

Implementa:
1. Pipeline de Pré-Processamento de Texto (`clean_and_normalize_text_ptbr`):
   - Extração de Hashtags (`#`) e Menções (`@`).
   - Remoção de tags HTML (`<br/>`), URLs (`http/https`), pontuação repetida e ruídos.
   - Normalização Unicode NFKD (remoção de acentos para pareamento léxico determinístico).
   - Remoção de Stopwords PT-BR preservando operadores lógicos de Negação e Intensificadores.
2. Analisador Contextual de Polaridade PT-BR (`LexiconSentimentAnalyzerPTBR`):
   - Dicionário de polaridade graduada (`-3.0` a `+3.0`).
   - Janela de Inversão por Negação (`window = 3` tokens: "não é bom" -> negativo; "não trava" -> positivo).
   - Amplificação/Atenuação por Intensificadores ("muito excelente", "extremamente lento").
   - Normalização não-linear VADER-style para `compound_sentiment_score` em `[-1.0, +1.0]`.
3. Derivação de NPS Simulado (`PROMOTER` 9-10, `PASSIVE` 7-8, `DETRACTOR` 0-6) e Engajamento Ponderado.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Any, Tuple

from src.config import (
    COMPOUND_ALPHA,
    NEGATIVE_CUTOFF,
    POSITIVE_CUTOFF,
    PTBR_INTENSIFIERS,
    PTBR_NEGATION_WORDS,
    PTBR_SENTIMENT_LEXICON,
    PTBR_STOPWORDS,
    RAW_REVIEWS_JSON_PATH,
)

HTML_TAG_REGEX = re.compile(r"<[^>]+>")
URL_REGEX = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
HASHTAG_REGEX = re.compile(r"#([A-Za-zÀ-ÿ0-9_]+)")
MENTION_REGEX = re.compile(r"@([A-Za-z0-9_]+)")
TOKEN_REGEX = re.compile(r"[a-z0-9]+")
WHITESPACE_REGEX = re.compile(r"\s+")


def strip_accents(text: str) -> str:
    """Remove diacríticos/acentos via decomposição Unicode NFKD."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def clean_and_normalize_text_ptbr(raw_text: str) -> Dict[str, Any]:
    """
    Executa a limpeza estruturada de um texto de avaliação/rede social:
    1. Extrai hashtags e menções.
    2. Remove HTML, URLs, menções e hashtags do corpo textual.
    3. Gera texto limpo legível e lista de tokens normalizados sem stopwords.
    """
    hashtags = [strip_accents(h.lower()) for h in HASHTAG_REGEX.findall(raw_text)]
    mentions = [m.lower() for m in MENTION_REGEX.findall(raw_text)]

    text_no_html = HTML_TAG_REGEX.sub(" ", raw_text)
    text_no_url = URL_REGEX.sub(" ", text_no_html)
    text_no_tags = HASHTAG_REGEX.sub(" ", MENTION_REGEX.sub(" ", text_no_url))
    cleaned_readable = WHITESPACE_REGEX.sub(" ", text_no_tags).strip()

    ascii_lower = strip_accents(cleaned_readable.lower())
    raw_tokens = TOKEN_REGEX.findall(ascii_lower)

    # Remove stopwords, mas preserva todas as palavras de negação e intensificadores
    filtered_tokens = [
        tok
        for tok in raw_tokens
        if tok not in PTBR_STOPWORDS
        or tok in PTBR_NEGATION_WORDS
        or tok in PTBR_INTENSIFIERS
    ]

    return {
        "cleaned_text": cleaned_readable,
        "tokens": filtered_tokens,
        "hashtags": hashtags,
        "mentions": mentions,
        "token_count": len(filtered_tokens),
    }


def score_sentiment_ptbr(
    tokens: List[str], hashtags: List[str] | None = None
) -> Dict[str, Any]:
    """
    Calcula o sentimento contextual de uma lista de tokens PT-BR utilizando:
    - Dicionário Léxico `PTBR_SENTIMENT_LEXICON`
    - Janela de Negação de até 3 tokens antecedentes (fator `-0.85`)
    - Modificadores de Intensidade antecedentes (`PTBR_INTENSIFIERS`)
    - Hashtags com peso complementar (`0.5x`)
    """
    matched_terms: List[Tuple[str, float]] = []
    negation_triggered = 0
    intensifier_triggered = 0

    for idx, token in enumerate(tokens):
        if token not in PTBR_SENTIMENT_LEXICON:
            continue

        base_weight = PTBR_SENTIMENT_LEXICON[token]
        if base_weight == 0.0:
            matched_terms.append((token, 0.0))
            continue

        # Inspeciona janela antecedente de até 3 tokens
        window_start = max(0, idx - 3)
        preceding_window = tokens[window_start:idx]

        weight = base_weight

        # 1. Verifica presença de intensificador na janela antecedente
        for prev_tok in preceding_window:
            if prev_tok in PTBR_INTENSIFIERS:
                weight *= PTBR_INTENSIFIERS[prev_tok]
                intensifier_triggered = 1

        # 2. Verifica presença de operador de negação na janela antecedente
        if any(prev_tok in PTBR_NEGATION_WORDS for prev_tok in preceding_window):
            weight *= -0.85
            negation_triggered = 1

        matched_terms.append((token, round(weight, 3)))

    # Avalia hashtags caso também constem no léxico (ex: #recomendo, #decepcao, #amei)
    if hashtags:
        for h in hashtags:
            if h in PTBR_SENTIMENT_LEXICON:
                matched_terms.append((f"#{h}", round(PTBR_SENTIMENT_LEXICON[h] * 0.5, 3)))

    raw_polarity_sum = round(sum(w for _, w in matched_terms), 3)

    # Normalização VADER-like para [-1.0, +1.0]: S = x / sqrt(x^2 + alpha)
    if raw_polarity_sum == 0.0:
        compound_score = 0.0
    else:
        compound_score = round(
            raw_polarity_sum / math.sqrt((raw_polarity_sum ** 2) + COMPOUND_ALPHA),
            4,
        )

    if compound_score >= POSITIVE_CUTOFF:
        sentiment_label = "POSITIVE"
    elif compound_score <= NEGATIVE_CUTOFF:
        sentiment_label = "NEGATIVE"
    else:
        sentiment_label = "NEUTRAL"

    # Mapeamento determinístico para escala NPS Simulado (0 a 10) e Segmento NPS
    if compound_score >= 0.65:
        nps_score = 10
        nps_segment = "PROMOTER"
    elif compound_score >= 0.30:
        nps_score = 9
        nps_segment = "PROMOTER"
    elif compound_score >= -0.14:
        nps_score = 8 if compound_score >= 0.0 else 7
        nps_segment = "PASSIVE"
    elif compound_score >= -0.55:
        nps_score = 5 if compound_score >= -0.35 else 4
        nps_segment = "DETRACTOR"
    else:
        nps_score = 2 if compound_score >= -0.75 else 1
        nps_segment = "DETRACTOR"

    return {
        "raw_polarity_sum": raw_polarity_sum,
        "compound_sentiment_score": compound_score,
        "sentiment_label": sentiment_label,
        "nps_score": nps_score,
        "nps_segment": nps_segment,
        "negation_detected_flag": negation_triggered,
        "intensifier_detected_flag": intensifier_triggered,
        "matched_lexicon_terms": [t for t, _ in matched_terms],
        "matched_terms_detail": matched_terms,
    }


class SentimentAnalyticsProcessor:
    """Processa o arquivo JSON de avaliações aplicando limpeza textual, sentimento e métricas de engajamento."""

    def process_json_file(
        self, json_path: Path = RAW_REVIEWS_JSON_PATH
    ) -> List[Dict[str, Any]]:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        raw_reviews = payload["reviews"]
        return self.process_reviews(raw_reviews)

    def process_reviews(self, raw_reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched_rows: List[Dict[str, Any]] = []

        for r in raw_reviews:
            cleaned = clean_and_normalize_text_ptbr(r["raw_review_text"])
            sentiment = score_sentiment_ptbr(cleaned["tokens"], cleaned["hashtags"])

            eng = r["engagement_metrics"]
            impressions = int(eng["impressions"])
            likes = int(eng["likes_count"])
            comments = int(eng["comments_count"])
            shares = int(eng["shares_count"])
            saves = int(eng["saves_count"])

            total_interactions = likes + comments + shares + saves
            # Engajamento Ponderado: Likes (1x), Comentários (3x), Salvamentos (4x), Compartilhamentos (5x)
            weighted_engagement = (likes * 1) + (comments * 3) + (saves * 4) + (shares * 5)
            engagement_rate_pct = round(
                (total_interactions / max(1, impressions)) * 100.0, 2
            )
            viral_impact_index = round(
                sentiment["compound_sentiment_score"]
                * math.log10(max(10.0, float(weighted_engagement))),
                3,
            )

            prod = r["product"]
            chan = r["channel"]
            date_key = r["review_timestamp"][:10]

            enriched_rows.append(
                {
                    "review_id": r["review_id"],
                    "customer_id": r["customer_id"],
                    "author_handle": r["author_handle"],
                    "customer_uf": r["customer_uf"],
                    "verified_purchase": 1 if r["verified_purchase"] else 0,
                    "review_timestamp": r["review_timestamp"],
                    "date_key": date_key,
                    "product_id": prod["product_id"],
                    "product_name": prod["product_name"],
                    "category_id": prod["category_id"],
                    "category_name": prod["category_name"],
                    "brand_tier": prod["brand_tier"],
                    "unit_price_brl": float(prod["unit_price_brl"]),
                    "channel_id": chan["channel_id"],
                    "channel_name": chan["channel_name"],
                    "platform_type": chan["platform_type"],
                    "raw_review_text": r["raw_review_text"],
                    "cleaned_review_text": cleaned["cleaned_text"],
                    "token_count": cleaned["token_count"],
                    "hashtags_extracted": ", ".join(cleaned["hashtags"]),
                    "raw_polarity_sum": sentiment["raw_polarity_sum"],
                    "compound_sentiment_score": sentiment["compound_sentiment_score"],
                    "sentiment_label": sentiment["sentiment_label"],
                    "nps_score": sentiment["nps_score"],
                    "nps_segment": sentiment["nps_segment"],
                    "negation_detected_flag": sentiment["negation_detected_flag"],
                    "intensifier_detected_flag": sentiment["intensifier_detected_flag"],
                    "matched_lexicon_terms": ", ".join(sentiment["matched_lexicon_terms"]),
                    "impressions": impressions,
                    "likes_count": likes,
                    "comments_count": comments,
                    "shares_count": shares,
                    "saves_count": saves,
                    "total_interactions": total_interactions,
                    "weighted_engagement_score": weighted_engagement,
                    "engagement_rate_pct": engagement_rate_pct,
                    "viral_impact_index": viral_impact_index,
                }
            )

        return enriched_rows
