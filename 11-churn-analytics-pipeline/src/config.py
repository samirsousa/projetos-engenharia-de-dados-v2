"""
Configurações centrais do projeto 11-churn-analytics-pipeline.
Define diretórios de dados, caminhos do banco SQLite analítico, diretórios de exportação
para Power BI (Star Schema) e parâmetros de negócio de SaaS (Planos, CAC, Margem Bruta).
"""

from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_OLTP_DIR = DATA_DIR / "raw_oltp"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
POWERBI_MART_DIR = DATA_DIR / "powerbi_mart"
SQL_DIR = PROJECT_ROOT / "sql"
REPORTS_DIR = PROJECT_ROOT / "reports"

SQLITE_DB_PATH = WAREHOUSE_DIR / "saas_churn_analytics.db"
ANALYTICAL_SQL_PATH = SQL_DIR / "analytical_queries.sql"

# Parâmetros Financeiros e de Produto SaaS B2B
GROSS_MARGIN_PCT: float = 0.82  # 82% de Margem Bruta típica de SaaS Cloud

SAAS_PLANS: Dict[str, Dict[str, Any]] = {
    "PLN-STARTER": {
        "plan_id": "PLN-STARTER",
        "plan_name": "Starter Cloud",
        "tier_level": 1,
        "base_mrr_brl": 199.00,
        "annual_discount_pct": 0.15,
        "base_monthly_churn_prob": 0.068,  # SMBs possuem maior sensibilidade a preço/churn
        "expansion_prob": 0.035,
        "contraction_prob": 0.010,
        "gross_margin_pct": 0.80,
        "included_seats": 3,
    },
    "PLN-GROWTH": {
        "plan_id": "PLN-GROWTH",
        "plan_name": "Growth Professional",
        "tier_level": 2,
        "base_mrr_brl": 599.00,
        "annual_discount_pct": 0.15,
        "base_monthly_churn_prob": 0.036,  # Mid-market com maior retenção e expansão
        "expansion_prob": 0.055,
        "contraction_prob": 0.018,
        "gross_margin_pct": 0.83,
        "included_seats": 10,
    },
    "PLN-ENTERPRISE": {
        "plan_id": "PLN-ENTERPRISE",
        "plan_name": "Enterprise Scale",
        "tier_level": 3,
        "base_mrr_brl": 1899.00,
        "annual_discount_pct": 0.15,
        "base_monthly_churn_prob": 0.014,  # Contratos corporativos com baixo logo churn e alto NRR
        "expansion_prob": 0.075,
        "contraction_prob": 0.015,
        "gross_margin_pct": 0.85,
        "included_seats": 50,
    },
}

ACQUISITION_CHANNELS: Dict[str, Dict[str, Any]] = {
    "Organic Search (SEO)": {"cac_brl": 420.00, "weight": 0.28, "churn_multiplier": 0.90},
    "Paid Search (Google Ads)": {"cac_brl": 950.00, "weight": 0.27, "churn_multiplier": 1.10},
    "Outbound Sales (SDR/AE)": {"cac_brl": 2150.00, "weight": 0.18, "churn_multiplier": 0.78},
    "Partner & Referral": {"cac_brl": 380.00, "weight": 0.15, "churn_multiplier": 0.82},
    "Paid Social (LinkedIn)": {"cac_brl": 1280.00, "weight": 0.12, "churn_multiplier": 1.18},
}

CHURN_REASONS = [
    ("Budget / Cost Reduction", "Voluntary", 0.29),
    ("Low Product Adoption / Onboarding Gap", "Voluntary", 0.24),
    ("Switched to Competitor", "Voluntary", 0.17),
    ("Missing Enterprise Feature / Integration", "Voluntary", 0.12),
    ("Company Closed / M&A Restructuring", "Voluntary", 0.06),
    ("Involuntary - Credit Card Expired / Hard Decline", "Involuntary", 0.12),
]


def ensure_directories() -> None:
    """Garante que toda a árvore de diretórios do projeto exista."""
    for directory in (RAW_OLTP_DIR, WAREHOUSE_DIR, POWERBI_MART_DIR, SQL_DIR, REPORTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
