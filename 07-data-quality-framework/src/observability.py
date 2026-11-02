"""
Camada de Observabilidade de Dados: Logs de Violação de Contrato e Despacho de Alertas.

Responsável por:
1. Gravar o Log Detalhado de Anomalias (`Data Contract Violation Log`) em JSON e `.log`.
2. Formatar e emitir Alertas em Texto (`Incident Alert Banner`) em caso de quebra de contrato.
3. Consolidar um Relatório Executivo de Data Quality & Observability em Markdown.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import DQConfig, setup_logger
from src.contracts import RuleSeverity, ValidationReport

logger = setup_logger("DQ-Observability")


class ObservabilityReporter:
    """Gerenciador de logs de anomalias (Data Contract Violations) e alertas operacionais."""

    def __init__(self, config: Optional[DQConfig] = None) -> None:
        self.config = config or DQConfig()
        self.config.ensure_directories()

    def write_anomaly_logs(self, report: ValidationReport) -> Tuple[Path, Path]:
        """
        Gera o log detalhado de anomalias (Data Contract Violation) em formato JSON
        estruturado e adiciona entradas ao arquivo central `data_contract_violations.log`.
        """
        slug = report.contract.dataset_name.lower().replace(" ", "_")
        json_log_path = self.config.anomalies_dir / f"violations_{slug}.json"
        central_log_path = self.config.anomalies_dir / "data_contract_violations.log"

        payload: Dict[str, Any] = {
            "event_type": "DATA_CONTRACT_VIOLATION" if not report.contract_passed else "DATA_CONTRACT_COMPLIANT",
            "run_id": report.run_id,
            "evaluated_at_utc": report.evaluated_at_utc,
            "contract_id": report.contract.contract_id,
            "dataset_name": report.contract.dataset_name,
            "source_format": report.contract.source_format,
            "source_identifier": report.source_identifier,
            "owner_team": report.contract.owner_team,
            "contract_passed": report.contract_passed,
            "metrics": {
                "total_rows": report.total_rows,
                "healthy_rows": report.healthy_rows_count,
                "corrupted_rows": report.corrupted_rows_count,
                "data_quality_score_pct": report.data_quality_score,
                "total_anomalies": len(report.anomalies),
                "violations_by_category": report.violations_by_category,
                "execution_time_ms": report.execution_time_ms,
            },
            "rule_summaries": [
                {
                    **asdict(summary),
                    "pass_rate_pct": summary.pass_rate,
                    "failure_rate_pct": summary.failure_rate,
                }
                for summary in report.rule_summaries
            ],
            "anomalies": [asdict(a) for a in report.anomalies],
        }

        with open(json_log_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

        if report.anomalies:
            with open(central_log_path, "a", encoding="utf-8") as log_fh:
                for anomaly in report.anomalies:
                    log_line = (
                        f"{report.evaluated_at_utc} | RUN={report.run_id} | "
                        f"CONTRACT={report.contract.contract_id} | SOURCE={report.source_identifier} | "
                        f"SEVERITY={anomaly.severity.value} | CATEGORY={anomaly.rule_category} | "
                        f"RULE={anomaly.rule_name} | COL={anomaly.column_name} | "
                        f"ROW={anomaly.row_index} | PK={anomaly.record_pk} | "
                        f"OBSERVED={repr(anomaly.observed_value)} | EXPECTED=\"{anomaly.expected_constraint}\" | "
                        f"MSG=\"{anomaly.diagnostic_message}\"\n"
                    )
                    log_fh.write(log_line)

        logger.info(
            "Log de anomalias registrado | dataset=%s | anomalias=%d | arquivo=%s",
            report.contract.dataset_name,
            len(report.anomalies),
            json_log_path.name,
        )
        return json_log_path, central_log_path

    def format_text_alert(self, report: ValidationReport) -> str:
        """
        Constrói um alerta formatado em texto puro (padrão Incident Response / PagerDuty)
        detalhando a quebra do Data Contract, métricas de impacto e anomalias críticas.
        """
        highest_severity = RuleSeverity.WARNING.value
        for anomaly in report.anomalies:
            if anomaly.severity == RuleSeverity.CRITICAL:
                highest_severity = RuleSeverity.CRITICAL.value
                break
            if anomaly.severity == RuleSeverity.ERROR:
                highest_severity = RuleSeverity.ERROR.value

        cat_counts = report.violations_by_category
        border = "=" * 88
        sub_border = "-" * 88

        lines = [
            border,
            f" [ALERTA DE CONFIABILIDADE DE DADOS] VIOLAÇÃO DE DATA CONTRACT ({highest_severity})",
            border,
            f" Run ID             : {report.run_id}",
            f" Timestamp (UTC)    : {report.evaluated_at_utc}",
            f" Contrato Violado   : {report.contract.contract_id} ({report.contract.dataset_name})",
            f" Fonte / Formato    : {report.source_identifier} [{report.contract.source_format}]",
            f" Equipe Responsável : {report.contract.owner_team}",
            f" Status do Pipeline : BLOQUEADO (CIRCUIT BREAKER ATIVADO - ENVIO PARA DLQ)",
            sub_border,
            " RESUMO DE IMPACTO E QUALIDADE (SLI / SLO):",
            f"   - Total de Registros Inspecionados : {report.total_rows}",
            f"   - Registros Saudáveis (Conformes)  : {report.healthy_rows_count}",
            f"   - Registros Corrompidos            : {report.corrupted_rows_count}",
            f"   - Score de Qualidade (DQ Score)    : {report.data_quality_score:.2f}%",
            f"   - Total de Violações Detectadas    : {len(report.anomalies)}",
            f"   - Nulidade (NULLABILITY)           : {cat_counts.get('NULLABILITY', 0)} falha(s)",
            f"   - Unicidade de IDs (UNIQUENESS)    : {cat_counts.get('UNIQUENESS', 0)} falha(s)",
            f"   - Limites de Valor (RANGE_CHECK)   : {cat_counts.get('RANGE_CHECK', 0)} falha(s)",
            f"   - Tipo de Dado (DATA_TYPE)         : {cat_counts.get('DATA_TYPE', 0)} falha(s)",
            sub_border,
            " DETALHAMENTO DAS ANOMALIAS DETECTADAS (DATA CONTRACT VIOLATIONS):",
        ]

        for anomaly in report.anomalies[:20]:
            lines.append(
                f"   [{anomaly.violation_id}] [{anomaly.severity.value}] {anomaly.rule_category:<12} | "
                f"Linha={str(anomaly.row_index):<3} | PK={str(anomaly.record_pk):<12} | "
                f"Coluna='{anomaly.column_name}' | Valor={repr(anomaly.observed_value)} "
                f"(Esperado: {anomaly.expected_constraint})"
            )

        if len(report.anomalies) > 20:
            lines.append(f"   ... (+{len(report.anomalies) - 20} anomalias adicionais no log JSON)")

        lines.extend(
            [
                sub_border,
                " AÇÃO RECOMENDADA DE ENGENHARIA (PLAYBOOK SRE / DATA RELIABILITY):",
                "   1. Isolar os registros listados acima na Dead-Letter Queue (DLQ).",
                f"   2. Notificar o time '{report.contract.owner_team}' sobre regressão no produtor upstream.",
                f"   3. Inspecionar o log completo em: logs/anomalies/violations_{report.contract.dataset_name.lower().replace(' ', '_')}.json",
                border,
                "",
            ]
        )
        return "\n".join(lines)

    def dispatch_alert_if_needed(
        self, report: ValidationReport, print_to_console: bool = True
    ) -> Optional[Path]:
        """
        Se o relatório apresentar falha no Data Contract, emite e persiste o alerta em texto.
        Retorna o caminho do arquivo de alerta gerado ou None se o dataset estiver íntegro.
        """
        if report.contract_passed and not report.anomalies:
            logger.info(
                "Dataset '%s' (%s) 100%% aderente ao Data Contract '%s'. Nenhum alerta disparado.",
                report.contract.dataset_name,
                report.contract.source_format,
                report.contract.contract_id,
            )
            return None

        alert_text = self.format_text_alert(report)
        slug = report.contract.dataset_name.lower().replace(" ", "_")
        alert_path = self.config.alerts_dir / f"alert_{slug}.txt"

        with open(alert_path, "w", encoding="utf-8") as fh:
            fh.write(alert_text)

        if print_to_console:
            print("\n" + alert_text)

        logger.warning(
            "Alerta de violação de contrato emitido | dataset=%s | arquivo=%s",
            report.contract.dataset_name,
            alert_path.name,
        )
        return alert_path

    def generate_consolidated_markdown_report(self, reports: List[ValidationReport]) -> Path:
        """Gera um relatório executivo consolidado em Markdown cobrindo todas as fontes avaliadas."""
        report_path = self.config.reports_dir / "dq_observability_report.md"

        lines = [
            "# Relatório Executivo de Data Quality & Observability",
            "",
            "Consolidação da bateria de testes de **Data Contracts** executada sobre arquivos **CSV**, **Apache Parquet** e tabelas **SQLite**.",
            "",
            "## 1. Visão Geral de Saúde dos Datasets (SLIs de Qualidade)",
            "",
            "| Contrato ID | Dataset | Formato | Linhas Totais | Saudáveis | Corrompidas | DQ Score (%) | Anomalias | Status do Contrato |",
            "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for rep in reports:
            status_badge = "APROVADO (PASS)" if rep.contract_passed else "VIOLADO (FAIL)"
            lines.append(
                f"| `{rep.contract.contract_id}` | `{rep.contract.dataset_name}` | **{rep.contract.source_format}** | "
                f"{rep.total_rows} | {rep.healthy_rows_count} | {rep.corrupted_rows_count} | "
                f"`{rep.data_quality_score:.2f}%` | `{len(rep.anomalies)}` | **{status_badge}** |"
            )

        lines.extend(["", "---", "", "## 2. Detalhamento por Fonte e Violações de Contrato", ""])

        for rep in reports:
            lines.extend(
                [
                    f"### 2.{reports.index(rep) + 1}. `{rep.contract.dataset_name}` ({rep.contract.source_format} — `{rep.source_identifier}`)",
                    "",
                    f"- **Run ID:** `{rep.run_id}` | **Equipe Responsável:** `{rep.contract.owner_team}` | **Tempo de Execução:** `{rep.execution_time_ms:.2f} ms`",
                    f"- **Data Quality Score:** `{rep.data_quality_score:.2f}%` ({rep.healthy_rows_count}/{rep.total_rows} registros conformes)",
                    "",
                    "#### Resumo de Regras Avaliadas",
                    "",
                    "| Categoria | Regra | Coluna | Avaliados | Falhas | Taxa de Sucesso | Status |",
                    "| :--- | :--- | :--- | :---: | :---: | :---: | :---: |",
                ]
            )
            for summary in rep.rule_summaries:
                st = "OK" if summary.passed else "FALHA"
                lines.append(
                    f"| `{summary.rule_category}` | `{summary.rule_name}` | `{summary.column_name}` | "
                    f"{summary.total_evaluated} | {summary.failed_count} | `{summary.pass_rate:.2f}%` | **{st}** |"
                )

            if rep.anomalies:
                lines.extend(
                    [
                        "",
                        "#### Anomalias Capturadas (Data Contract Violations)",
                        "",
                        "| ID | Categoria | Severidade | Linha | PK | Coluna | Valor Observado | Restrição Esperada | Diagnóstico |",
                        "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
                    ]
                )
                for anom in rep.anomalies:
                    lines.append(
                        f"| `{anom.violation_id}` | `{anom.rule_category}` | **{anom.severity.value}** | "
                        f"`{anom.row_index}` | `{anom.record_pk}` | `{anom.column_name}` | "
                        f"`{repr(anom.observed_value)}` | `{anom.expected_constraint}` | {anom.diagnostic_message} |"
                    )
            else:
                lines.extend(["", "> Nenhuma anomalia detectada. Dataset 100% em conformidade com o contrato."])

            lines.append("")

        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

        logger.info("Relatório consolidado Markdown salvo em: %s", report_path)
        return report_path
