"""
Script 2: Leitor / Conector CDC (Simulador Debezium) que monitora o WAL e emite logs JSON.
Ponto de entrada CLI direto para o Componente 2 do pipeline CDC.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cdc_connector import main

if __name__ == "__main__":
    main()
