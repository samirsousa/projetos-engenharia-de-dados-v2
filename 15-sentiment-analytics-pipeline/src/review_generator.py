"""
Gerador de Avaliações de Clientes e Menções de Redes Sociais em Formato JSON (Stage 1).

Simula um arquivo JSON bruto (`customer_social_reviews.json`) com 1.250 avaliações em Português (pt-BR),
contendo textos com ruídos reais de redes sociais (URLs, tags HTML, menções `@`, hashtags `#`,
acentuação, estruturas de negação como "não recomendo" / "não é bom" e intensificadores como
"extremamente rápido" / "muito péssimo"), além de métricas de alcance e engajamento.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple

from src.config import (
    PRODUCT_CATALOG,
    RAW_REVIEWS_JSON_PATH,
    SOCIAL_CHANNELS,
    ensure_directories,
)

POSITIVE_TEMPLATES = [
    "Produto muito excelente e super rápido! A bateria é durável e o acabamento impecável. #Recomendo #Top @TechStoreBR https://loja.tech/p/{pid}",
    "Simplesmente perfeito! Comprei e chegou antes do prazo, muito prático, silencioso e eficiente. Nota10 demais! <br/> #CompraCerta",
    "Adorei a qualidade! Extremamente potente, bonito e estável no dia a dia. Vale cada centavo, super aprovado!",
    "Surpreendente! Eu achava que seria comum, mas é maravilhoso e muito confortável. #Amei #QualidadePremium",
    "Ótimo custo e desempenho excelente! Fluido, rápido e resistente. Estou totalmente satisfeito com a aquisição!",
    "Sensacional! Não trava nunca e funciona de forma impecável. Recomendadíssimo para quem busca desempenho!",
]

NEGATIVE_TEMPLATES = [
    "Péssimo investimento! Muito frágil, esquenta demais e a bateria descarrega rápido. Decepção total! #Arrependido @SuporteTech",
    "Horrível! Com duas semanas de uso apresentou defeito e parou de funcionar. O suporte demorou e atrasou a troca! <br/> http://reclame.io/{pid}",
    "Não é bom! Na propaganda parecia excelente, mas na prática é muito lento, instável e barulhento. Não recomendo para ninguém!",
    "Experiência terrível e decepcionante. Produto quebrado na caixa, acabamento fraco e totalmente inútil. Pior compra do ano! #Problema",
    "Infelizmente não cumpre o que promete. Nunca fica estável, vive travando e tem chiado constante. Muito insatisfeito!",
    "Caro demais para uma qualidade tão ruim! Estragou rápido e jamais voltaria a comprar dessa linha. #Decepcao",
]

NEUTRAL_TEMPLATES = [
    "Produto normal e básico. Funciona de forma regular para tarefas simples do cotidiano. #ReviewSincero",
    "Razoável pelo preço pago. O acabamento é comum e aceitável, sem grandes surpresas no uso diário.",
    "Atende de forma ok. É um aparelho mediano e básico, entrega apenas o esperado para a faixa de entrada.",
    "Recebi ontem. Embalagem normal, funcionamento regular até o momento. Vamos testar nas próximas semanas. @TechStoreBR",
]

STATES_UF = ["SP", "RJ", "MG", "PR", "RS", "SC", "BA", "PE", "CE", "DF", "GO"]


class SocialReviewJSONGenerator:
    """Gerador determinístico de payloads JSON de avaliações de clientes e engajamento social."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_reviews_payload(self, total_reviews: int = 1250) -> Dict[str, Any]:
        reviews: List[Dict[str, Any]] = []
        base_dt = datetime(2026, 8, 1, 9, 0, 0)

        for idx in range(1, total_reviews + 1):
            review_id = f"REV-{idx:05d}"
            customer_id = f"CUST-{self.rng.randint(1001, 1650):04d}"
            product = self.rng.choice(PRODUCT_CATALOG)
            channel = self.rng.choice(SOCIAL_CHANNELS)
            uf = self.rng.choices(
                STATES_UF, weights=[34, 14, 11, 8, 7, 6, 5, 4, 4, 4, 3]
            )[0]

            # Sorteio de sentimento base condicionado à qualidade histórica da categoria/produto
            roll = self.rng.random()
            pos_prob = product["positive_bias"]
            neg_prob = (1.0 - pos_prob) * 0.72

            if roll < pos_prob:
                template = self.rng.choice(POSITIVE_TEMPLATES)
                expected_tone = "POSITIVE"
                # Postagens positivas e negativas extremas geram maior engajamento orgânico
                virality_mult = self.rng.uniform(0.95, 2.15)
            elif roll < (pos_prob + neg_prob):
                template = self.rng.choice(NEGATIVE_TEMPLATES)
                expected_tone = "NEGATIVE"
                virality_mult = self.rng.uniform(1.15, 2.65)
            else:
                template = self.rng.choice(NEUTRAL_TEMPLATES)
                expected_tone = "NEUTRAL"
                virality_mult = self.rng.uniform(0.55, 1.15)

            raw_text = template.format(pid=product["product_id"].lower())

            # Métricas de Engajamento de Rede Social (Impressões, Likes, Comentários, Shares, Saves)
            impressions = int(
                round(channel["base_impressions"] * virality_mult * self.rng.uniform(0.75, 1.40))
            )
            likes = int(round(impressions * self.rng.uniform(0.035, 0.115)))
            comments = int(
                round(
                    likes
                    * (
                        self.rng.uniform(0.14, 0.34)
                        if expected_tone == "NEGATIVE"
                        else self.rng.uniform(0.06, 0.18)
                    )
                )
            )
            shares = int(round(likes * self.rng.uniform(0.04, 0.22)))
            saves = int(round(likes * self.rng.uniform(0.05, 0.19)))

            review_dt = base_dt + timedelta(
                days=self.rng.randint(0, 89),
                hours=self.rng.randint(0, 23),
                minutes=self.rng.randint(0, 59),
            )

            reviews.append(
                {
                    "review_id": review_id,
                    "customer_id": customer_id,
                    "author_handle": f"@user_br_{customer_id.lower().replace('-', '_')}",
                    "customer_uf": uf,
                    "verified_purchase": True if self.rng.random() < 0.86 else False,
                    "review_timestamp": review_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "product": {
                        "product_id": product["product_id"],
                        "product_name": product["product_name"],
                        "category_id": product["category_id"],
                        "category_name": product["category_name"],
                        "brand_tier": product["brand_tier"],
                        "unit_price_brl": product["unit_price_brl"],
                    },
                    "channel": {
                        "channel_id": channel["channel_id"],
                        "channel_name": channel["channel_name"],
                        "platform_type": channel["platform_type"],
                    },
                    "raw_review_text": raw_text,
                    "engagement_metrics": {
                        "impressions": impressions,
                        "likes_count": likes,
                        "comments_count": comments,
                        "shares_count": shares,
                        "saves_count": saves,
                    },
                }
            )

        reviews.sort(key=lambda r: r["review_timestamp"])
        return {
            "dataset_metadata": {
                "pipeline_name": "15-sentiment-analytics-pipeline",
                "language": "pt-BR",
                "generated_at": "2026-11-02T10:00:00-03:00",
                "total_reviews": len(reviews),
            },
            "reviews": reviews,
        }


def save_reviews_json(
    total_reviews: int = 1250,
    seed: int = 42,
    output_path: Path = RAW_REVIEWS_JSON_PATH,
) -> Dict[str, Any]:
    """Gera e persiste o arquivo JSON de avaliações de clientes."""
    ensure_directories()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gen = SocialReviewJSONGenerator(seed=seed)
    payload = gen.generate_reviews_payload(total_reviews=total_reviews)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "json_path": str(output_path),
        "total_reviews": len(payload["reviews"]),
    }
