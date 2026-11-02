"""
Etapa 2: Execução do Motor Estatístico de Detecção de Anomalias (Z-Score, MAD e Regras)
e persistência da tabela `suspect_transactions` no banco de dados relacional.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import SQLITE_DB_PATH
from src.fraud_engine import StatisticalFraudDetectionEngine


def main() -> None:
    engine = StatisticalFraudDetectionEngine(db_path=SQLITE_DB_PATH)
    results = engine.run_detection()
    m = results["metrics"]

    print("=" * 80)
    print("[ETAPA 2] DETECÇÃO DE ANOMALIAS (Z-SCORE & BASELINES) CONCLUÍDA")
    print("=" * 80)
    print(f"  -> Transações Analisadas         : {m['total_transactions']:,}")
    print(f"  -> Transações em 'suspect_transactions': {m['total_suspect_flagged']:,}")
    print(f"  -> Precision: {m['precision_pct']:.2f}% | Recall: {m['recall_pct']:.2f}% | F1: {m['f1_score_pct']:.2f}%")
    print(f"  -> Fraudes Evitadas (Capital Protegido): R$ {m['prevented_fraud_loss_brl']:,.2f}")


if __name__ == "__main__":
    main()
