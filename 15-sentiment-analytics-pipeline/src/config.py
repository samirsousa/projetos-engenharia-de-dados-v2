"""
Configurações centrais do Projeto 15: Social Media Sentiment & Engagement Analytics Pipeline.
Define diretórios, catálogo de produtos e categorias, canais de mídia social,
dicionário léxico de polaridade PT-BR, modificadores de negação/intensidade e pesos de engajamento.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_JSON_DIR = DATA_DIR / "raw_json"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
DASHBOARD_MART_DIR = DATA_DIR / "dashboard_mart"
REPORTS_DIR = PROJECT_ROOT / "reports"

RAW_REVIEWS_JSON_PATH = RAW_JSON_DIR / "customer_social_reviews.json"
SQLITE_DB_PATH = WAREHOUSE_DIR / "sentiment_analytics_dw.db"

# Constante de Normalização VADER-like para o Score Composto [-1.0, +1.0]
COMPOUND_ALPHA: float = 12.0
POSITIVE_CUTOFF: float = 0.15
NEGATIVE_CUTOFF: float = -0.15

# Catálogo de Produtos e Categorias
PRODUCT_CATALOG: List[Dict[str, Any]] = [
    {
        "product_id": "PRD-SM-01",
        "product_name": "Smartphone Horizon Pro 5G 256GB",
        "category_id": "CAT-MOBILE",
        "category_name": "Smartphones & Wearables",
        "brand_tier": "Flagship Premium",
        "unit_price_brl": 3899.00,
        "positive_bias": 0.68,
    },
    {
        "product_id": "PRD-SM-02",
        "product_name": "Smartwatch PulseFit AMOLED GPS",
        "category_id": "CAT-MOBILE",
        "category_name": "Smartphones & Wearables",
        "brand_tier": "Mid-Range Tech",
        "unit_price_brl": 899.00,
        "positive_bias": 0.64,
    },
    {
        "product_id": "PRD-NB-01",
        "product_name": "Notebook TitanBook Ultra RTX 16GB",
        "category_id": "CAT-COMPUTING",
        "category_name": "Notebooks & Hardware Gamer",
        "brand_tier": "Performance Pro",
        "unit_price_brl": 6499.00,
        "positive_bias": 0.74,
    },
    {
        "product_id": "PRD-NB-02",
        "product_name": "Monitor Curvo 165Hz IPS 27 Pol",
        "category_id": "CAT-COMPUTING",
        "category_name": "Notebooks & Hardware Gamer",
        "brand_tier": "Performance Pro",
        "unit_price_brl": 1599.00,
        "positive_bias": 0.71,
    },
    {
        "product_id": "PRD-AU-01",
        "product_name": "Fone Bluetooth SonicPods ANC",
        "category_id": "CAT-AUDIO",
        "category_name": "Áudio & Fones Bluetooth",
        "brand_tier": "Consumer Audio",
        "unit_price_brl": 449.00,
        "positive_bias": 0.42,  # Categoria com lote de bateria defeituosa simulando detratores de NPS
    },
    {
        "product_id": "PRD-AU-02",
        "product_name": "Caixa de Som BoomBox Waterproof 60W",
        "category_id": "CAT-AUDIO",
        "category_name": "Áudio & Fones Bluetooth",
        "brand_tier": "Consumer Audio",
        "unit_price_brl": 699.00,
        "positive_bias": 0.56,
    },
    {
        "product_id": "PRD-IOT-01",
        "product_name": "Robô Aspirador SmartClean Laser LiDAR",
        "category_id": "CAT-SMARTHOME",
        "category_name": "Casa Inteligente & IoT",
        "brand_tier": "Smart Home",
        "unit_price_brl": 2199.00,
        "positive_bias": 0.77,
    },
    {
        "product_id": "PRD-IOT-02",
        "product_name": "Fechadura Digital Biometria Wi-Fi",
        "category_id": "CAT-SMARTHOME",
        "category_name": "Casa Inteligente & IoT",
        "brand_tier": "Smart Home",
        "unit_price_brl": 799.00,
        "positive_bias": 0.69,
    },
    {
        "product_id": "PRD-CAF-01",
        "product_name": "Cafeteira Espresso Barista Pro 19 Bar",
        "category_id": "CAT-APPLIANCES",
        "category_name": "Eletroportáteis & Café",
        "brand_tier": "Home Kitchen",
        "unit_price_brl": 1299.00,
        "positive_bias": 0.61,
    },
    {
        "product_id": "PRD-CAF-02",
        "product_name": "AirFryer Digital Oven Inox 12L",
        "category_id": "CAT-APPLIANCES",
        "category_name": "Eletroportáteis & Café",
        "brand_tier": "Home Kitchen",
        "unit_price_brl": 749.00,
        "positive_bias": 0.66,
    },
]

SOCIAL_CHANNELS: List[Dict[str, Any]] = [
    {"channel_id": "CH-IG", "channel_name": "Instagram Reels & Feed", "platform_type": "Social Video/Photo", "base_impressions": 4800},
    {"channel_id": "CH-TK", "channel_name": "TikTok Shop & Creators", "platform_type": "Short-Form Video", "base_impressions": 7200},
    {"channel_id": "CH-YT", "channel_name": "YouTube Tech Reviews", "platform_type": "Long-Form Video", "base_impressions": 3900},
    {"channel_id": "CH-EC", "channel_name": "E-Commerce Verified Reviews", "platform_type": "Marketplace Portal", "base_impressions": 1100},
    {"channel_id": "CH-TW", "channel_name": "X / Twitter Mentions", "platform_type": "Microblogging", "base_impressions": 2600},
]

# Dicionário Léxico de Polaridade PT-BR (Chaves normalizadas sem acento para matching robusto)
# Escala de pesos: [-3.0 (Extremamente Negativo) a +3.0 (Extremamente Positivo)]
PTBR_SENTIMENT_LEXICON: Dict[str, float] = {
    # Termos Positivos Fortes (+2.0 a +3.0)
    "excelente": 2.8,
    "perfeito": 2.9,
    "perfeita": 2.9,
    "maravilhoso": 2.8,
    "maravilhosa": 2.8,
    "sensacional": 2.7,
    "incrivel": 2.7,
    "impecavel": 2.8,
    "espetacular": 2.8,
    "amei": 2.6,
    "adoro": 2.4,
    "adorei": 2.5,
    "recomendo": 2.3,
    "recomendadissimo": 2.9,
    "surpreendente": 2.4,
    "surpreendeu": 2.3,
    "otimo": 2.3,
    "otima": 2.3,
    "nota10": 2.7,
    "top": 1.8,
    # Termos Positivos Moderados (+1.0 a +1.9)
    "bom": 1.5,
    "boa": 1.5,
    "rapido": 1.7,
    "rapida": 1.7,
    "eficiente": 1.8,
    "duravel": 1.9,
    "resistente": 1.8,
    "silencioso": 1.6,
    "silenciosa": 1.6,
    "pratico": 1.6,
    "pratica": 1.6,
    "bonito": 1.4,
    "lindo": 1.7,
    "fluido": 1.8,
    "estavel": 1.7,
    "confortavel": 1.7,
    "potente": 1.9,
    "economico": 1.6,
    "satisfeito": 2.1,
    "satisfeita": 2.1,
    "cumpre": 1.4,
    "aprovado": 2.0,
    "vale": 1.5,
    "compensa": 1.6,
    # Termos Neutros / Ambíguos Leves (-0.4 a +0.4)
    "razoavel": 0.1,
    "mediano": -0.2,
    "comum": 0.0,
    "basico": 0.0,
    "normal": 0.1,
    "ok": 0.2,
    "aceitavel": 0.2,
    "regular": -0.2,
    # Termos Negativos Moderados (-1.0 a -1.9)
    "ruim": -1.8,
    "lento": -1.7,
    "lenta": -1.7,
    "caro": -1.3,
    "cara": -1.3,
    "fraco": -1.6,
    "fraca": -1.6,
    "barulhento": -1.5,
    "instavel": -1.7,
    "demorou": -1.6,
    "atraso": -1.8,
    "atrasou": -1.8,
    "confuso": -1.3,
    "fragil": -1.7,
    "esquenta": -1.6,
    "descarrega": -1.8,
    "chiado": -1.7,
    "insatisfeito": -2.1,
    "insatisfeita": -2.1,
    # Termos Negativos Fortes (-2.0 a -3.0)
    "pessimo": -2.8,
    "pessima": -2.8,
    "horrivel": -2.9,
    "terrivel": -2.8,
    "lixo": -3.0,
    "decepcao": -2.6,
    "decepcionado": -2.5,
    "decepcionante": -2.6,
    "defeito": -2.5,
    "defeituoso": -2.6,
    "quebrou": -2.7,
    "quebrado": -2.6,
    "travando": -2.3,
    "trava": -2.2,
    "parou": -2.4,
    "estragou": -2.6,
    "arrependido": -2.6,
    "arrependimento": -2.7,
    "propaganda": -1.5,
    "enganosa": -2.8,
    "golpe": -3.0,
    "inutil": -2.7,
    "desastre": -2.8,
    "pior": -2.5,
}

# Palavras de Negação em Português (invertem a polaridade dos próximos até 3 tokens)
PTBR_NEGATION_WORDS: Set[str] = {
    "nao",
    "nunca",
    "jamais",
    "nem",
    "sem",
    "nenhum",
    "nenhuma",
    "nada",
    "tampouco",
}

# Modificadores de Intensidade (Boosters & Downtoners)
PTBR_INTENSIFIERS: Dict[str, float] = {
    "muito": 1.35,
    "super": 1.40,
    "extremamente": 1.50,
    "totalmente": 1.35,
    "completamente": 1.35,
    "bastante": 1.25,
    "demais": 1.30,
    "realmente": 1.20,
    "pouco": 0.55,
    "levemente": 0.60,
    "quase": 0.65,
}

# Stopwords PT-BR (Excluindo explicitamente negações e intensificadores!)
PTBR_STOPWORDS: Set[str] = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "por", "para", "com", "como", "que", "se", "ou",
    "e", "mas", "porem", "todavia", "meu", "minha", "meus", "minhas", "seu", "sua",
    "este", "esta", "isso", "isto", "aquele", "aquela", "foi", "era", "ser", "estar",
    "esta", "estou", "tem", "ter", "tive", "comprei", "produto", "aparelho", "item",
    "dia", "dias", "mes", "uso", "usar", "ate", "ao", "aos", "pelo", "pela", "ja",
}


def ensure_directories() -> None:
    """Garante que toda a árvore de diretórios do projeto exista."""
    for d in (RAW_JSON_DIR, WAREHOUSE_DIR, DASHBOARD_MART_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
