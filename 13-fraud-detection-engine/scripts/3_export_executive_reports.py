"""
Etapa 3: Exportação Executiva em CSV, Planilha Excel (.xls Multi-Abas / CSV PT-BR) e Relatório Markdown.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import EXPORTS_DIR, SQLITE_DB_PATH
from src.fraud_engine import StatisticalFraudDetectionEngine
from src.report_exporter import (
    export_executive_csv_and_excel,
    generate_markdown_executive_report,
)


def main() -> None:
    engine = StatisticalFraudDetectionEngine(db_path=SQLITE_DB_PATH)
    results = engine.run_detection()
    exported = export_executive_csv_and_excel(results, exports_dir=EXPORTS_DIR)
    report_path = generate_markdown_executive_report(results)

    print("=" * 80)
    print("[ETAPA 3] EXPORTAÇÃO EXECUTIVA CSV / EXCEL E RELATÓRIO DE AUDITORIA")
    print("=" * 80)
    for k, v in exported.items():
        print(f"  -> {k:<26}: {v}")
    print(f"  -> markdown_report           : {report_path}")


if __name__ == "__main__":
    main()
