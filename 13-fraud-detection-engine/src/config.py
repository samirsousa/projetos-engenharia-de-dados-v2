"""
Configurações centrais do Projeto 13: Sistema de Alerta de Anomalias em Transações Financeiras.
Define diretórios, perfis estatísticos de usuários (Baselines teóricos), limiares de Z-Score,
Modified Z-Score (MAD), regras de velocidade/geolocalização e pesos do Score de Risco.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_TX_DIR = DATA_DIR / "raw_transactions"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
EXPORTS_DIR = DATA_DIR / "exports"
REPORTS_DIR = PROJECT_ROOT / "reports"

SQLITE_DB_PATH = WAREHOUSE_DIR / "fraud_detection.db"

# Limiares Estatísticos de Detecção de Anomalias
Z_SCORE_WARNING_THRESHOLD: float = 2.50     # ~98.76% de confiança bilateral
Z_SCORE_SUSPECT_THRESHOLD: float = 3.00     # Regra de Shewhart / 3-Sigma (~99.73%)
Z_SCORE_CRITICAL_THRESHOLD: float = 4.20    # Anomalia severa (> 4.2 desvios padrão)
MODIFIED_Z_SCORE_THRESHOLD: float = 3.50    # Critério robusto de Iglewicz & Hoaglin (baseado em MAD)
IMPOSSIBLE_TRAVEL_SPEED_KMH: float = 800.0  # Velocidade geodésica incompatível com deslocamento terrestre/comercial sem escala
VELOCITY_BURST_WINDOW_MINUTES: float = 8.0  # Transações sucessivas em janela curta (ataque automatizado / script)
COMPOSITE_SUSPECT_CUTOFF: float = 50.0      # Score mínimo [0..100] para inserção em suspect_transactions

# Perfis de Clientes Financeiros (Segmentação de Comportamento de Gasto)
CUSTOMER_PROFILES: Dict[str, Dict[str, Any]] = {
    "RETAIL_BASIC": {
        "profile_code": "RETAIL_BASIC",
        "profile_name": "Varejo Essencial PF",
        "weight": 0.42,
        "mean_amount_brl": 145.00,
        "std_amount_brl": 48.00,
        "monthly_income_brl": 4200.00,
        "typical_tx_per_user": 22,
    },
    "AFFLUENT_PLUS": {
        "profile_code": "AFFLUENT_PLUS",
        "profile_name": "Alta Renda Personalizado PF",
        "weight": 0.30,
        "mean_amount_brl": 680.00,
        "std_amount_brl": 210.00,
        "monthly_income_brl": 18500.00,
        "typical_tx_per_user": 25,
    },
    "PRIVATE_WEALTH": {
        "profile_code": "PRIVATE_WEALTH",
        "profile_name": "Private Banking & Investidor",
        "weight": 0.12,
        "mean_amount_brl": 2850.00,
        "std_amount_brl": 820.00,
        "monthly_income_brl": 68000.00,
        "typical_tx_per_user": 24,
    },
    "SME_CORPORATE": {
        "profile_code": "SME_CORPORATE",
        "profile_name": "PME & Conta Empresarial PJ",
        "weight": 0.16,
        "mean_amount_brl": 4600.00,
        "std_amount_brl": 1350.00,
        "monthly_income_brl": 145000.00,
        "typical_tx_per_user": 26,
    },
}

# Coordenadas de Domicílio Bancário dos Clientes
HOME_CITIES: List[Dict[str, Any]] = [
    {"city": "São Paulo", "uf": "SP", "lat": -23.5505, "lon": -46.6333},
    {"city": "Rio de Janeiro", "uf": "RJ", "lat": -22.9068, "lon": -43.1729},
    {"city": "Belo Horizonte", "uf": "MG", "lat": -19.9167, "lon": -43.9345},
    {"city": "Curitiba", "uf": "PR", "lat": -25.4284, "lon": -49.2733},
    {"city": "Porto Alegre", "uf": "RS", "lat": -30.0346, "lon": -51.2177},
    {"city": "Brasília", "uf": "DF", "lat": -15.7975, "lon": -47.8919},
    {"city": "Salvador", "uf": "BA", "lat": -12.9714, "lon": -38.5014},
    {"city": "Recife", "uf": "PE", "lat": -8.0476, "lon": -34.8770},
]

# Categorias de Estabelecimento (MCC) e Nível de Risco Intrínseco
MERCHANT_CATEGORIES: List[Dict[str, Any]] = [
    {"mcc_code": "5411", "category": "Supermercados & Alimentação", "is_high_risk_mcc": 0},
    {"mcc_code": "5812", "category": "Restaurantes & Delivery", "is_high_risk_mcc": 0},
    {"mcc_code": "5541", "category": "Postos de Combustível & Pedágio", "is_high_risk_mcc": 0},
    {"mcc_code": "5912", "category": "Farmácias & Saúde", "is_high_risk_mcc": 0},
    {"mcc_code": "5732", "category": "Eletrônicos & Informática", "is_high_risk_mcc": 0},
    {"mcc_code": "4829", "category": "Transferência PIX / P2P Instantâneo", "is_high_risk_mcc": 1},
    {"mcc_code": "6051", "category": "Criptoativos & Câmbio Internacional", "is_high_risk_mcc": 1},
    {"mcc_code": "5944", "category": "Joalheria & Relojoaria de Luxo", "is_high_risk_mcc": 1},
    {"mcc_code": "7995", "category": "Apostas Online & Cassinos (iGaming)", "is_high_risk_mcc": 1},
]

PAYMENT_CHANNELS = [
    "PIX_INSTANT",
    "CREDIT_CARD_CHIP",
    "CREDIT_CARD_VIRTUAL_CNP",
    "DEBIT_CONTACTLESS",
    "TED_WIRE",
]


def ensure_directories() -> None:
    """Garante que toda a estrutura de diretórios do projeto exista."""
    for d in (RAW_TX_DIR, WAREHOUSE_DIR, EXPORTS_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
