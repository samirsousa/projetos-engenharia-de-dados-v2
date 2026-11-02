"""
Script 3: Consumidor em Lote da Camada Silver e Gerador de Relatório Diário de Auditoria.
Ponto de entrada CLI direto para o Componente 3 do pipeline CDC.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.silver_consumer import main

if __name__ == "__main__":
    main()
