"""
Etapa 1: Geração do Arquivo de Log Simulado de Servidores (`centralized_cluster_access.log`).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.log_generator import write_simulated_log_file


def main() -> None:
    meta = write_simulated_log_file(total_lines=3200, seed=42)
    print("=" * 80)
    print("[ETAPA 1] ARQUIVO DE LOG DE SERVIDORES GERADO COM SUCESSO")
    print("=" * 80)
    print(f"  -> Arquivo gerado        : {meta['log_file_path']}")
    print(f"  -> Total de linhas       : {meta['total_lines']:,}")
    print(f"  -> Linhas corrompidas DLQ: {meta['expected_corrupted_lines']}")


if __name__ == "__main__":
    main()
