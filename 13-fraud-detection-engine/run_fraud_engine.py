"""
Orquestrador End-to-End do Projeto 13: Sistema de Alerta de Anomalias em Transações Financeiras.

Executa sequencialmente:
1. Geração e carga de clientes e transações financeiras com tipologias de fraude (`raw_customers`, `raw_transactions`).
2. Cálculo de baselines estatísticos por perfil e por usuário (Média, Desvio Padrão, Mediana, MAD, Limite 3-Sigma)
   e detecção de anomalias via Z-Score / Modified Z-Score / Velocidade Geoespacial, populando `suspect_transactions`.
3. Exportação de relatórios executivos em CSV, Excel PT-BR (`;`), Planilha Excel Multi-Abas (`.xls`) e Markdown.
"""

from __future__ import annotations

import argparse
import shutil
import time
from typing import Dict, Any

from src.config import (
    DATA_DIR,
    EXPORTS_DIR,
    RAW_TX_DIR,
    REPORTS_DIR,
    SQLITE_DB_PATH,
    ensure_directories,
)
from src.fraud_engine import StatisticalFraudDetectionEngine
from src.report_exporter import (
    export_executive_csv_and_excel,
    generate_markdown_executive_report,
)
from src.transaction_generator import (
    FinancialTransactionSimulator,
    save_raw_transactions_and_load_db,
)


def run_fraud_pipeline(
    clean: bool = False,
    seed: int = 42,
    num_customers: int = 100,
) -> Dict[str, Any]:
    start_ts = time.perf_counter()

    if clean:
        for d in (DATA_DIR, REPORTS_DIR):
            if d.exists():
                shutil.rmtree(d)

    ensure_directories()

    print("=" * 86)
    print("  PROJETO 13: SISTEMA DE ALERTA DE ANOMALIAS EM TRANSAÇÕES FINANCEIRAS (FRAUD ENGINE)")
    print("=" * 86)

    # 1. Geração e Carga da Base Transacional
    print("\n[1/3] Gerando base transacional financeira e perfis de usuários...")
    simulator = FinancialTransactionSimulator(seed=seed)
    dataset = simulator.generate_dataset(num_customers=num_customers)
    raw_counts = save_raw_transactions_and_load_db(
        dataset, raw_dir=RAW_TX_DIR, db_path=SQLITE_DB_PATH
    )
    print(f"      - Clientes cadastrados (`raw_customers`)    : {raw_counts['raw_customers']:,}")
    print(f"      - Transações geradas (`raw_transactions`)   : {raw_counts['raw_transactions']:,}")

    # 2. Motor Estatístico de Baselines e Z-Score
    print("\n[2/3] Calculando baselines (Média, Desvio Padrão, MAD) e aplicando Z-Score...")
    engine = StatisticalFraudDetectionEngine(db_path=SQLITE_DB_PATH)
    detection_results = engine.run_detection()
    m = detection_results["metrics"]
    print(f"      - Baselines de Perfil calculados            : {len(detection_results['profile_baselines'])}")
    print(f"      - Baselines Individuais de Usuário          : {len(detection_results['user_baselines'])}")
    print(f"      - Transações Suspeitas (`suspect_transactions`): {m['total_suspect_flagged']:,}")

    # 3. Exportação Executiva CSV / Excel / Markdown
    print("\n[3/3] Exportando relatórios executivos (CSV, Excel Multi-Abas .xls e Markdown)...")
    exported_files = export_executive_csv_and_excel(
        detection_results, exports_dir=EXPORTS_DIR
    )
    report_path = generate_markdown_executive_report(detection_results)

    elapsed = time.perf_counter() - start_ts

    print("\n" + "=" * 86)
    print("  RESUMO EXECUTIVO DO MOTOR DE DETECÇÃO DE ANOMALIAS E FRAUDES")
    print("=" * 86)
    print(f"  * Total de Transações Processadas        : {m['total_transactions']:,}")
    print(f"  * Alertas Gerados (`suspect_transactions`): {m['total_suspect_flagged']:,} ({m['alert_rate_pct']:.2f}%)")
    print(f"  * Z-Score Médio dos Alertas              : +{m['avg_suspect_z_score']:.2f} sigma (Máx: +{m['max_suspect_z_score']:.2f} sigma)")
    print("-" * 86)
    print(f"  * Verdadeiros Positivos (Fraudes Pegas)  : {m['true_positives']}")
    print(f"  * Falsos Positivos (Alertas em Legítimas): {m['false_positives']} (FPR: {m['false_positive_rate_pct']:.2f}%)")
    print(f"  * Falsos Negativos                       : {m['false_negatives']}")
    print(f"  * Precisão (Precision)                   : {m['precision_pct']:.2f}%")
    print(f"  * Cobertura de Fraudes (Recall)          : {m['recall_pct']:.2f}%")
    print(f"  * F1-Score Global                        : {m['f1_score_pct']:.2f}%")
    print("-" * 86)
    print(f"  * Volume Total Transacionado             : R$ {m['total_transacted_volume_brl']:,.2f}")
    print(f"  * Perda Financeira Evitada (R$ Protegido): R$ {m['prevented_fraud_loss_brl']:,.2f}")
    print("-" * 86)
    print(f"  * Banco SQLite (`suspect_transactions`)  : {SQLITE_DB_PATH}")
    print(f"  * Planilha Executiva Excel Multi-Abas    : {exported_files['excel_workbook_xls']}")
    print(f"  * CSV Executivo (Padrão & Excel PT-BR)   : {exported_files['suspect_excel_ptbr_csv']}")
    print(f"  * Relatório Executivo Markdown           : {report_path}")
    print("=" * 86)
    print(f"Motor de Detecção concluído com sucesso em {elapsed:.2f}s.\n")

    return {
        "raw_counts": raw_counts,
        "metrics": m,
        "exported_files": exported_files,
        "report_path": str(report_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa o Motor de Detecção de Anomalias Financeiras (Z-Score & Baselines)."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove artefatos anteriores antes de executar.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed aleatória para reprodutibilidade determinística (padrão: 42).",
    )
    args = parser.parse_args()
    run_fraud_pipeline(clean=args.clean, seed=args.seed)


if __name__ == "__main__":
    main()
