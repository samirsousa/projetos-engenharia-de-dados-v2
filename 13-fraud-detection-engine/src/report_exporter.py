"""
Exportador de Relatórios Executivos em CSV, Planilha Excel Multi-Abas e Markdown (Stage 3).

Gera:
1. `data/exports/suspect_transactions.csv` (CSV padrão internacional UTF-8 `,`)
2. `data/exports/suspect_transactions_excel_ptbr.csv` (CSV UTF-8-BOM com separador `;` nativo para Excel PT-BR)
3. `data/exports/user_statistical_baselines.csv` & `profile_statistical_baselines.csv`
4. `data/exports/fraud_executive_workbook.xls` (Planilha Microsoft Excel XML SpreadsheetML multi-abas:
   - Aba 1: `Resumo_Executivo_KPIs`
   - Aba 2: `Baselines_Por_Perfil`
   - Aba 3: `Suspect_Transactions`)
5. `reports/fraud_detection_executive_report.md` (Relatório Executivo Técnico em Markdown)
"""

from __future__ import annotations

import csv
from html import escape
from pathlib import Path
from typing import Dict, List, Any

from src.config import EXPORTS_DIR, REPORTS_DIR, ensure_directories


def _write_csv(
    rows: List[Dict[str, Any]],
    path: Path,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding=encoding)
        return path
    fieldnames = list(rows[0].keys())
    with open(path, mode="w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _build_excel_xml_worksheet(sheet_name: str, rows: List[Dict[str, Any]]) -> str:
    """Constrói uma aba (Worksheet) no formato Microsoft Office Excel 2003 XML (SpreadsheetML)."""
    if not rows:
        return f'<Worksheet ss:Name="{escape(sheet_name)}"><Table></Table></Worksheet>'

    headers = list(rows[0].keys())
    xml_lines = [f'  <Worksheet ss:Name="{escape(sheet_name[:31])}">', "    <Table>"]

    # Cabeçalho estilizado
    xml_lines.append('      <Row ss:StyleID="HeaderStyle">')
    for h in headers:
        xml_lines.append(
            f'        <Cell><Data ss:Type="String">{escape(str(h))}</Data></Cell>'
        )
    xml_lines.append("      </Row>")

    # Linhas de dados
    for r in rows:
        xml_lines.append("      <Row>")
        for h in headers:
            val = r[h]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                xml_lines.append(
                    f'        <Cell><Data ss:Type="Number">{val}</Data></Cell>'
                )
            else:
                xml_lines.append(
                    f'        <Cell><Data ss:Type="String">{escape(str(val))}</Data></Cell>'
                )
        xml_lines.append("      </Row>")

    xml_lines.append("    </Table>")
    xml_lines.append("  </Worksheet>")
    return "\n".join(xml_lines)


def export_executive_csv_and_excel(
    detection_results: Dict[str, Any],
    exports_dir: Path = EXPORTS_DIR,
) -> Dict[str, str]:
    """Exporta todos os artefatos executivos em CSV, CSV-Excel PT-BR e Planilha Multi-Abas .xls."""
    ensure_directories()
    exports_dir.mkdir(parents=True, exist_ok=True)

    suspect_rows = detection_results["suspect_transactions"]
    user_baselines = detection_results["user_baselines"]
    profile_baselines = detection_results["profile_baselines"]
    metrics = detection_results["metrics"]

    # 1. CSVs Padrão e CSV Otimizado para Excel PT-BR (UTF-8 com BOM e delimitador ';')
    suspect_csv = _write_csv(
        suspect_rows, exports_dir / "suspect_transactions.csv", delimiter=",", encoding="utf-8"
    )
    suspect_excel_csv = _write_csv(
        suspect_rows,
        exports_dir / "suspect_transactions_excel_ptbr.csv",
        delimiter=";",
        encoding="utf-8-sig",
    )
    user_base_csv = _write_csv(
        user_baselines,
        exports_dir / "user_statistical_baselines.csv",
        delimiter=",",
        encoding="utf-8",
    )
    profile_base_csv = _write_csv(
        profile_baselines,
        exports_dir / "profile_statistical_baselines.csv",
        delimiter=",",
        encoding="utf-8",
    )

    # 2. Planilha Executiva Multi-Abas (.xls SpreadsheetML)
    kpi_rows = [{"Indicador_Executivo": k, "Valor": v} for k, v in metrics.items()]
    workbook_xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<?mso-application progid="Excel.Sheet"?>',
            '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
            ' xmlns:o="urn:schemas-microsoft-com:office:office"',
            ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
            ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">',
            "  <Styles>",
            '    <Style ss:ID="HeaderStyle">',
            '      <Font ss:Bold="1" ss:Color="#FFFFFF"/>',
            '      <Interior ss:Color="#1E3A8A" ss:Pattern="Solid"/>',
            "    </Style>",
            "  </Styles>",
            _build_excel_xml_worksheet("1_Resumo_Executivo", kpi_rows),
            _build_excel_xml_worksheet("2_Baselines_Por_Perfil", profile_baselines),
            _build_excel_xml_worksheet("3_Baselines_Por_Usuario", user_baselines),
            _build_excel_xml_worksheet("4_Suspect_Transactions", suspect_rows),
            "</Workbook>",
        ]
    )
    excel_workbook_path = exports_dir / "fraud_executive_workbook.xls"
    excel_workbook_path.write_text(workbook_xml, encoding="utf-8")

    return {
        "suspect_csv": str(suspect_csv),
        "suspect_excel_ptbr_csv": str(suspect_excel_csv),
        "user_baselines_csv": str(user_base_csv),
        "profile_baselines_csv": str(profile_base_csv),
        "excel_workbook_xls": str(excel_workbook_path),
    }


def generate_markdown_executive_report(
    detection_results: Dict[str, Any],
    report_path: Path = REPORTS_DIR / "fraud_detection_executive_report.md",
) -> Path:
    """Gera o relatório executivo em Markdown com análise estatística, baselines e top alertas."""
    report_path.parent.mkdir(parents=True, exist_ok=True)

    metrics = detection_results["metrics"]
    profile_baselines = detection_results["profile_baselines"]
    suspect_rows = detection_results["suspect_transactions"]

    lines = [
        "# Relatório Executivo: Sistema de Alerta de Anomalias e Fraudes Financeiras",
        "",
        "## 1. Sumário Executivo de Desempenho Estatístico & Prevenção a Perdas",
        "",
        "| Indicador do Motor Antifraude | Valor Consolidado | Observação Técnica |",
        "| :--- | ---: | :--- |",
        f"| **Total de Transações Analisadas** | `{metrics['total_transactions']:,}` | Base histórica e eventos de risco |",
        f"| **Transações Suspeitas (`suspect_transactions`)** | `{metrics['total_suspect_flagged']:,}` | Taxa de alerta de `{metrics['alert_rate_pct']:.2f}%` |",
        f"| **Volume Financeiro Total Transacionado** | `R$ {metrics['total_transacted_volume_brl']:,.2f}` | Soma bruta das operações |",
        f"| **Perda Financeira Evitada (Fraudes Bloqueadas)** | **`R$ {metrics['prevented_fraud_loss_brl']:,.2f}`** | Capital protegido pelo motor |",
        f"| **Z-Score Médio das Transações Suspeitas** | `{metrics['avg_suspect_z_score']:.2f} σ` | Pico máximo de `{metrics['max_suspect_z_score']:.2f} σ` |",
        f"| **Precisão Estatística (Precision)** | `{metrics['precision_pct']:.2f}%` | `TP = {metrics['true_positives']}` / `FP = {metrics['false_positives']}` |",
        f"| **Sensibilidade / Cobertura de Fraude (Recall)** | `{metrics['recall_pct']:.2f}%` | `TP = {metrics['true_positives']}` / `FN = {metrics['false_negatives']}` |",
        f"| **F1-Score Global** | **`{metrics['f1_score_pct']:.2f}%`** | Harmônica entre Precisão e Recall |",
        f"| **Taxa de Falso Positivo (FPR)** | `{metrics['false_positive_rate_pct']:.2f}%` | Fricção mínima sobre clientes legítimos |",
        "",
        "---",
        "",
        "## 2. Baselines Estatísticos por Perfil de Cliente (`profile_statistical_baselines`)",
        "",
        "| Código do Perfil | Transações | Média Bruta (R$) | Desvio Bruto (R$) | Média Baseline Limpa $\\mu$ (R$) | Desvio Baseline $\\sigma$ (R$) | Mediana (R$) | MAD (R$) | P95 (R$) | Limite $3\\sigma$ (R$) |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for p in profile_baselines:
        lines.append(
            f"| `{p['profile_code']}` | {p['tx_count']:,} | {p['raw_mean_brl']:,.2f} | "
            f"{p['raw_std_brl']:,.2f} | **{p['baseline_mean_brl']:,.2f}** | "
            f"**{p['baseline_std_brl']:,.2f}** | {p['median_brl']:,.2f} | "
            f"{p['mad_brl']:,.2f} | {p['p95_brl']:,.2f} | `{p['upper_3sigma_limit_brl']:,.2f}` |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Top 20 Transações Críticas Sinalizadas em `suspect_transactions`",
            "",
            "| TXN ID | Usuário | Perfil | Valor (R$) | Média Usuário (R$) | Desvio $\\sigma$ (R$) | Z-Score ($Z_u$) | Mod. Z ($M_u$) | Canal | Score Risco | Severidade | Regras Estatísticas Acionadas |",
            "| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- | ---: | :--- | :--- |",
        ]
    )

    for s in suspect_rows[:20]:
        lines.append(
            f"| `{s['transaction_id']}` | `{s['user_id']}` | `{s['profile_code']}` | "
            f"**{s['amount_brl']:,.2f}** | {s['user_baseline_mean_brl']:,.2f} | "
            f"{s['user_baseline_std_brl']:,.2f} | **`+{s['user_z_score']:.2f}σ`** | "
            f"`+{s['user_modified_z_score']:.2f}` | `{s['payment_channel']}` | "
            f"**`{s['composite_risk_score']:.1f}`** | `{s['risk_severity']}` | {s['triggered_rules']} |"
        )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
