"""
Configurações centrais do Projeto 14: Log Aggregator & Centralized Log Parser.
Define diretórios, limiares de SRE (Four Golden Signals, Apdex, SLO de Disponibilidade),
nós do cluster de servidores, rotas da API e perfis de tráfego/ataque.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_LOGS_DIR = DATA_DIR / "raw_logs"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
PARSED_EXPORTS_DIR = DATA_DIR / "parsed_exports"
REPORTS_DIR = PROJECT_ROOT / "reports"

RAW_LOG_FILE_PATH = RAW_LOGS_DIR / "centralized_cluster_access.log"
SQLITE_DB_PATH = WAREHOUSE_DIR / "centralized_logs.db"

# Parâmetros SRE (Site Reliability Engineering)
APDEX_SATISFIED_MS: float = 120.0   # Requisições <= 120ms = Satisfatórias
APDEX_TOLERATING_MS: float = 480.0  # Requisições <= 480ms = Toleráveis (> 480ms = Frustradas)
SLO_AVAILABILITY_TARGET_PCT: float = 98.50  # Meta de requisições sem erro 5xx

CLUSTER_NODES: List[str] = [
    "edge-ingress-01",
    "edge-ingress-02",
    "app-worker-01",
    "app-worker-02",
]

HTTP_STATUS_CATALOG: Dict[int, Dict[str, str]] = {
    200: {"class": "2xx Success", "description": "OK - Requisição processada com sucesso"},
    201: {"class": "2xx Success", "description": "Created - Recurso criado com sucesso"},
    204: {"class": "2xx Success", "description": "No Content - Processado sem corpo de resposta"},
    301: {"class": "3xx Redirection", "description": "Moved Permanently - Redirecionamento de URI"},
    400: {"class": "4xx Client Error", "description": "Bad Request - Payload ou query inválida"},
    401: {"class": "4xx Client Error", "description": "Unauthorized - Falha de autenticação / Token inválido"},
    403: {"class": "4xx Client Error", "description": "Forbidden - Acesso negado pelo WAF / RBAC"},
    404: {"class": "4xx Client Error", "description": "Not Found - Rota ou recurso inexistente"},
    429: {"class": "4xx Client Error", "description": "Too Many Requests - Rate Limit excedido"},
    500: {"class": "5xx Server Error", "description": "Internal Server Error - Exceção não tratada no backend"},
    502: {"class": "5xx Server Error", "description": "Bad Gateway - Falha de comunicação com upstream"},
    503: {"class": "5xx Server Error", "description": "Service Unavailable - Sobrecarga de pool de conexões"},
    504: {"class": "5xx Server Error", "description": "Gateway Timeout - Timeout de banco de dados / upstream"},
}

def ensure_directories() -> None:
    """Garante a existência de todos os diretórios de dados, banco e relatórios."""
    for d in (RAW_LOGS_DIR, WAREHOUSE_DIR, PARSED_EXPORTS_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
