"""
Definições declarativas de Contratos de Dados (Data Contracts) e estruturas de resultados.

Permite especificar expectativas formais sobre qualquer fonte tabular (CSV, Parquet ou SQLite):
- Nulidade de colunas-chave (Not Null)
- Unicidade de identificadores (Uniqueness / Primary Key)
- Limites de valores numéricos e domínios categóricos (Range & Domain Checks)
- Conformidade estrita de tipos primitivos e formatos semânticos (Data Type Checks)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class RuleSeverity(str, Enum):
    """Nível de criticidade operacional de uma violação de contrato."""

    CRITICAL = "CRITICAL"  # Bloqueia o pipeline (Circuit Breaker)
    ERROR = "ERROR"        # Envia registros para Dead-Letter Queue (DLQ) e dispara alerta
    WARNING = "WARNING"    # Registra degradação de SLA sem interromper o fluxo


class ExpectedDataType(str, Enum):
    """Tipos de dados suportados pelo validador semântico em Python puro."""

    INT = "INT"
    FLOAT = "FLOAT"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"              # ISO-8601: YYYY-MM-DD
    TIMESTAMP = "TIMESTAMP"    # ISO-8601: YYYY-MM-DDTHH:MM:SS
    EMAIL = "EMAIL"
    UUID = "UUID"


@dataclass
class ColumnContract:
    """Especificação de qualidade e restrições de domínio para uma coluna."""

    name: str
    expected_type: ExpectedDataType
    nullable: bool = True
    unique: bool = False
    is_primary_key: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    regex_pattern: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    severity: RuleSeverity = RuleSeverity.CRITICAL
    description: str = ""


@dataclass
class DataContract:
    """Contrato formal de qualidade de dados para um dataset ou tabela."""

    contract_id: str
    dataset_name: str
    source_format: str  # 'CSV', 'PARQUET', 'SQLITE'
    owner_team: str
    sla_freshness_hours: int = 24
    min_expected_rows: int = 1
    max_error_rate_threshold: float = 0.0
    primary_key_column: Optional[str] = None
    columns: List[ColumnContract] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, path: Path) -> DataContract:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        cols = [
            ColumnContract(
                name=c["name"],
                expected_type=ExpectedDataType(c["expected_type"]),
                nullable=bool(c.get("nullable", True)),
                unique=bool(c.get("unique", False)),
                is_primary_key=bool(c.get("is_primary_key", False)),
                min_value=c.get("min_value"),
                max_value=c.get("max_value"),
                allowed_values=c.get("allowed_values"),
                regex_pattern=c.get("regex_pattern"),
                min_length=c.get("min_length"),
                max_length=c.get("max_length"),
                severity=RuleSeverity(c.get("severity", "CRITICAL")),
                description=c.get("description", ""),
            )
            for c in raw.get("columns", [])
        ]
        return cls(
            contract_id=raw["contract_id"],
            dataset_name=raw["dataset_name"],
            source_format=raw["source_format"],
            owner_team=raw["owner_team"],
            sla_freshness_hours=int(raw.get("sla_freshness_hours", 24)),
            min_expected_rows=int(raw.get("min_expected_rows", 1)),
            max_error_rate_threshold=float(raw.get("max_error_rate_threshold", 0.0)),
            primary_key_column=raw.get("primary_key_column"),
            columns=cols,
        )


@dataclass
class AnomalyRecord:
    """Representa uma ocorrência individual de anomalia (Data Contract Violation)."""

    violation_id: str
    rule_category: str         # 'NULLABILITY', 'UNIQUENESS', 'RANGE_CHECK', 'DATA_TYPE', 'SCHEMA_CHECK'
    rule_name: str
    severity: RuleSeverity
    column_name: str
    row_index: Optional[int]   # Índice 1-based da linha no dataset (None para regras de tabela inteira)
    record_pk: Optional[str]   # Valor da chave primária da linha afetada para rastreabilidade
    observed_value: Any
    expected_constraint: str
    diagnostic_message: str


@dataclass
class RuleExecutionSummary:
    """Resumo estatístico da avaliação de uma regra específica sobre o dataset."""

    rule_category: str
    rule_name: str
    column_name: str
    severity: RuleSeverity
    total_evaluated: int
    failed_count: int
    passed: bool

    @property
    def pass_rate(self) -> float:
        if self.total_evaluated == 0:
            return 100.0
        return round(((self.total_evaluated - self.failed_count) / self.total_evaluated) * 100.0, 2)

    @property
    def failure_rate(self) -> float:
        if self.total_evaluated == 0:
            return 0.0
        return round((self.failed_count / self.total_evaluated) * 100.0, 2)


@dataclass
class ValidationReport:
    """Relatório consolidado da execução de um Data Contract sobre uma fonte de dados."""

    run_id: str
    evaluated_at_utc: str
    contract: DataContract
    source_identifier: str
    total_rows: int
    total_columns: int
    healthy_rows_count: int
    corrupted_rows_count: int
    rule_summaries: List[RuleExecutionSummary] = field(default_factory=list)
    anomalies: List[AnomalyRecord] = field(default_factory=list)
    execution_time_ms: float = 0.0

    @property
    def contract_passed(self) -> bool:
        """Retorna True se não houver violações CRITICAL/ERROR acima do limiar permitido."""
        blocking_anomalies = [
            a for a in self.anomalies if a.severity in (RuleSeverity.CRITICAL, RuleSeverity.ERROR)
        ]
        if not blocking_anomalies:
            return True
        if self.total_rows == 0:
            return False
        error_rate = self.corrupted_rows_count / self.total_rows
        return error_rate <= self.contract.max_error_rate_threshold

    @property
    def data_quality_score(self) -> float:
        """Índice percentual de linhas 100% aderentes ao contrato (0.0 a 100.0%)."""
        if self.total_rows == 0:
            return 0.0
        return round((self.healthy_rows_count / self.total_rows) * 100.0, 2)

    @property
    def violations_by_category(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for anomaly in self.anomalies:
            counts[anomaly.rule_category] = counts.get(anomaly.rule_category, 0) + 1
        return counts
