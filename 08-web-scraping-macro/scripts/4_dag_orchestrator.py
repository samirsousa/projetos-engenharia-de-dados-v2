"""
Script 4: Simulador de Orquestração em DAG Sequencial (Airflow / Cron Scheduler).
Ponto de entrada CLI numerado para o Componente 4 do projeto.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_dag import parse_args, run_scheduled_dag


if __name__ == "__main__":
    args = parse_args()
    run_scheduled_dag(clean_start=args.clean, simulate_failures=args.simulate_failures)
