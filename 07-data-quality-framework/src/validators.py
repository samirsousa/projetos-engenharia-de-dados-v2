"""
Motor de Validação de Data Quality em Python Puro (`DataQualityEngine`).

Implementa os 4 pilares fundamentais exigidos pelo Data Contract:
1. Nulidade de Colunas-Chave (`NULLABILITY` - Not Null Check)
2. Unicidade de IDs (`UNIQUENESS` - Primary Key & Duplicate ID Check)
3. Testes de Tipo de Dado (`DATA_TYPE` - Strict Type & Semantic Format Check)
4. Limites de Valores e Domínios (`RANGE_CHECK` - Min/Max Bounds, Allowed Set & Regex)
"""

from __future__ import annotations

import math
import re
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from src.connectors import TabularDataset
from src.contracts import (
    AnomalyRecord,
    ColumnContract,
    DataContract,
    ExpectedDataType,
    RuleExecutionSummary,
    RuleSeverity,
    ValidationReport,
)


NULL_STRING_TOKENS: Set[str] = {"", "null", "none", "nan", "n/a", "nil", "#n/a", "<na>"}

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class DataQualityEngine:
    """
    Motor modular de validação de contratos de dados em Python puro.
    Inspeciona cada registro de um `TabularDataset` contra um `DataContract`
    e produz um `ValidationReport` com rastreabilidade completa de anomalias.
    """

    @staticmethod
    def is_null_value(value: Any) -> bool:
        """Avalia se um valor deve ser tratado como nulo em CSV, Parquet ou SQLite."""
        if value is None:
            return True
        if isinstance(value, float) and math.isnan(value):
            return True
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.lower() in NULL_STRING_TOKENS:
                return True
        return False

    @staticmethod
    def validate_and_coerce_type(
        value: Any, expected_type: ExpectedDataType
    ) -> Tuple[bool, Optional[Any], str]:
        """
        Verifica se `value` respeita `expected_type` e retorna:
        `(is_valid, coerced_value, error_detail)`.
        """
        if expected_type == ExpectedDataType.INT:
            if isinstance(value, bool):
                return False, None, "Valor booleano encontrado onde era esperado INT"
            if isinstance(value, int):
                return True, value, ""
            if isinstance(value, float):
                if value.is_integer():
                    return True, int(value), ""
                return False, None, f"Float com parte decimal ({value}) inválido para INT"
            if isinstance(value, str):
                text = value.strip()
                if re.match(r"^[+-]?\d+$", text):
                    return True, int(text), ""
                return False, None, f"String '{value}' não representa um inteiro válido"
            return False, None, f"Tipo incompatível ({type(value).__name__}) para INT"

        if expected_type == ExpectedDataType.FLOAT:
            if isinstance(value, bool):
                return False, None, "Valor booleano encontrado onde era esperado FLOAT"
            if isinstance(value, (int, float)):
                if math.isnan(float(value)) or math.isinf(float(value)):
                    return False, None, "Valor numérico NaN/Inf inválido para FLOAT"
                return True, float(value), ""
            if isinstance(value, str):
                text = value.strip()
                try:
                    parsed = float(text)
                    if math.isnan(parsed) or math.isinf(parsed):
                        return False, None, "String NaN/Inf inválida para FLOAT"
                    return True, parsed, ""
                except ValueError:
                    return False, None, f"String '{value}' não pode ser convertida para FLOAT"
            return False, None, f"Tipo incompatível ({type(value).__name__}) para FLOAT"

        if expected_type == ExpectedDataType.BOOLEAN:
            if isinstance(value, bool):
                return True, value, ""
            if isinstance(value, int) and value in (0, 1):
                return True, bool(value), ""
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in ("true", "1", "yes", "t"):
                    return True, True, ""
                if lowered in ("false", "0", "no", "f"):
                    return True, False, ""
            return False, None, f"Valor '{value}' inválido para BOOLEAN"

        if expected_type == ExpectedDataType.DATE:
            if isinstance(value, date) and not isinstance(value, datetime):
                return True, value.isoformat(), ""
            if isinstance(value, str):
                text = value.strip()
                try:
                    parsed_date = date.fromisoformat(text)
                    return True, parsed_date.isoformat(), ""
                except ValueError:
                    return False, None, f"Data '{value}' fora do formato ISO-8601 (YYYY-MM-DD)"
            return False, None, f"Tipo '{type(value).__name__}' inválido para DATE"

        if expected_type == ExpectedDataType.TIMESTAMP:
            if isinstance(value, datetime):
                return True, value.isoformat(), ""
            if isinstance(value, str):
                text = value.strip().replace("Z", "+00:00")
                try:
                    datetime.fromisoformat(text)
                    return True, value.strip(), ""
                except ValueError:
                    return False, None, f"Timestamp '{value}' fora do padrão ISO-8601"
            return False, None, f"Tipo '{type(value).__name__}' inválido para TIMESTAMP"

        if expected_type == ExpectedDataType.EMAIL:
            if isinstance(value, str) and EMAIL_REGEX.match(value.strip()):
                return True, value.strip(), ""
            return False, None, f"Valor '{value}' não é um endereço de e-mail válido"

        if expected_type == ExpectedDataType.UUID:
            if isinstance(value, str) and UUID_REGEX.match(value.strip()):
                return True, value.strip(), ""
            return False, None, f"Valor '{value}' não é um UUID canônico"

        if expected_type == ExpectedDataType.STRING:
            if isinstance(value, str):
                return True, value, ""
            return False, None, f"Esperado STRING, mas recebido {type(value).__name__} ({value})"

        return True, value, ""

    def evaluate(self, dataset: TabularDataset, contract: DataContract) -> ValidationReport:
        """Executa toda a bateria de validações do contrato sobre o dataset."""
        start_ns = time.perf_counter_ns()
        run_id = f"DQ-RUN-{uuid.uuid4().hex[:8].upper()}"
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        anomalies: List[AnomalyRecord] = []
        rule_summaries: List[RuleExecutionSummary] = []
        corrupted_row_indices: Set[int] = set()
        violation_seq = 0

        def next_violation_id() -> str:
            nonlocal violation_seq
            violation_seq += 1
            return f"VIOL-{violation_seq:04d}"

        pk_col = contract.primary_key_column
        if not pk_col:
            for col in contract.columns:
                if col.is_primary_key:
                    pk_col = col.name
                    break

        # 0. Validação Estrutural de Schema e Volume Mínimo
        missing_cols = [c.name for c in contract.columns if c.name not in dataset.columns]
        for m_col in missing_cols:
            anomalies.append(
                AnomalyRecord(
                    violation_id=next_violation_id(),
                    rule_category="SCHEMA_CHECK",
                    rule_name="required_column_exists",
                    severity=RuleSeverity.CRITICAL,
                    column_name=m_col,
                    row_index=None,
                    record_pk=None,
                    observed_value="MISSING_COLUMN",
                    expected_constraint=f"Coluna '{m_col}' obrigatória no schema",
                    diagnostic_message=f"Coluna obrigatória '{m_col}' ausente na fonte {dataset.source_name}.",
                )
            )
        rule_summaries.append(
            RuleExecutionSummary(
                rule_category="SCHEMA_CHECK",
                rule_name="required_columns_exist",
                column_name="*",
                severity=RuleSeverity.CRITICAL,
                total_evaluated=len(contract.columns),
                failed_count=len(missing_cols),
                passed=len(missing_cols) == 0,
            )
        )

        # Avaliação por Coluna definida no Contrato
        for col_spec in contract.columns:
            if col_spec.name not in dataset.columns:
                continue

            col_name = col_spec.name
            null_failures = 0
            unique_failures = 0
            type_failures = 0
            range_failures = 0

            seen_values: Dict[Any, int] = {}
            non_null_evaluated = 0
            range_evaluated = 0

            has_range_or_domain_rules = any(
                v is not None
                for v in (
                    col_spec.min_value,
                    col_spec.max_value,
                    col_spec.allowed_values,
                    col_spec.regex_pattern,
                    col_spec.min_length,
                    col_spec.max_length,
                )
            )
            compiled_regex = re.compile(col_spec.regex_pattern) if col_spec.regex_pattern else None

            for idx, row in enumerate(dataset.rows, start=1):
                raw_val = row.get(col_name)
                pk_val = str(row.get(pk_col)) if (pk_col and row.get(pk_col) is not None) else f"ROW-{idx}"

                # 1. Teste de Nulidade (Not Null Check)
                if self.is_null_value(raw_val):
                    if not col_spec.nullable or col_spec.is_primary_key:
                        null_failures += 1
                        corrupted_row_indices.add(idx)
                        anomalies.append(
                            AnomalyRecord(
                                violation_id=next_violation_id(),
                                rule_category="NULLABILITY",
                                rule_name="not_null_check",
                                severity=col_spec.severity,
                                column_name=col_name,
                                row_index=idx,
                                record_pk=pk_val,
                                observed_value=raw_val,
                                expected_constraint="NOT NULL",
                                diagnostic_message=(
                                    f"Valor nulo ou vazio detectado na coluna-chave '{col_name}' "
                                    f"(linha {idx}, PK={pk_val})."
                                ),
                            )
                        )
                    continue

                non_null_evaluated += 1

                # 2. Teste de Tipo de Dado (Data Type Check)
                type_ok, coerced_val, type_err = self.validate_and_coerce_type(
                    raw_val, col_spec.expected_type
                )
                if not type_ok:
                    type_failures += 1
                    corrupted_row_indices.add(idx)
                    anomalies.append(
                        AnomalyRecord(
                            violation_id=next_violation_id(),
                            rule_category="DATA_TYPE",
                            rule_name=f"type_check_{col_spec.expected_type.value.lower()}",
                            severity=col_spec.severity,
                            column_name=col_name,
                            row_index=idx,
                            record_pk=pk_val,
                            observed_value=raw_val,
                            expected_constraint=f"TYPE == {col_spec.expected_type.value}",
                            diagnostic_message=(
                                f"Violação de tipo na coluna '{col_name}' (linha {idx}, PK={pk_val}): "
                                f"{type_err}."
                            ),
                        )
                    )
                    continue

                # 3. Teste de Unicidade de IDs (Uniqueness Check)
                if col_spec.unique or col_spec.is_primary_key:
                    if coerced_val in seen_values:
                        first_row = seen_values[coerced_val]
                        unique_failures += 1
                        corrupted_row_indices.add(idx)
                        anomalies.append(
                            AnomalyRecord(
                                violation_id=next_violation_id(),
                                rule_category="UNIQUENESS",
                                rule_name="unique_id_check",
                                severity=col_spec.severity,
                                column_name=col_name,
                                row_index=idx,
                                record_pk=pk_val,
                                observed_value=coerced_val,
                                expected_constraint="UNIQUE",
                                diagnostic_message=(
                                    f"ID duplicado '{coerced_val}' na coluna '{col_name}' "
                                    f"(linha {idx} colide com a linha {first_row})."
                                ),
                            )
                        )
                    else:
                        seen_values[coerced_val] = idx

                # 4. Teste de Limites de Valores e Domínio (Range & Domain Check)
                if has_range_or_domain_rules:
                    range_evaluated += 1
                    row_range_failed = False

                    if col_spec.min_value is not None and isinstance(coerced_val, (int, float)):
                        if float(coerced_val) < float(col_spec.min_value):
                            row_range_failed = True
                            anomalies.append(
                                AnomalyRecord(
                                    violation_id=next_violation_id(),
                                    rule_category="RANGE_CHECK",
                                    rule_name="min_value_bound",
                                    severity=col_spec.severity,
                                    column_name=col_name,
                                    row_index=idx,
                                    record_pk=pk_val,
                                    observed_value=coerced_val,
                                    expected_constraint=f">= {col_spec.min_value}",
                                    diagnostic_message=(
                                        f"Valor {coerced_val} abaixo do limite mínimo permitido "
                                        f"({col_spec.min_value}) na coluna '{col_name}' (linha {idx}, PK={pk_val})."
                                    ),
                                )
                            )

                    if col_spec.max_value is not None and isinstance(coerced_val, (int, float)):
                        if float(coerced_val) > float(col_spec.max_value):
                            row_range_failed = True
                            anomalies.append(
                                AnomalyRecord(
                                    violation_id=next_violation_id(),
                                    rule_category="RANGE_CHECK",
                                    rule_name="max_value_bound",
                                    severity=col_spec.severity,
                                    column_name=col_name,
                                    row_index=idx,
                                    record_pk=pk_val,
                                    observed_value=coerced_val,
                                    expected_constraint=f"<= {col_spec.max_value}",
                                    diagnostic_message=(
                                        f"Valor {coerced_val} acima do limite máximo permitido "
                                        f"({col_spec.max_value}) na coluna '{col_name}' (linha {idx}, PK={pk_val})."
                                    ),
                                )
                            )

                    if col_spec.allowed_values is not None:
                        if coerced_val not in col_spec.allowed_values:
                            row_range_failed = True
                            anomalies.append(
                                AnomalyRecord(
                                    violation_id=next_violation_id(),
                                    rule_category="RANGE_CHECK",
                                    rule_name="allowed_domain_values",
                                    severity=col_spec.severity,
                                    column_name=col_name,
                                    row_index=idx,
                                    record_pk=pk_val,
                                    observed_value=coerced_val,
                                    expected_constraint=f"IN {col_spec.allowed_values}",
                                    diagnostic_message=(
                                        f"Valor '{coerced_val}' fora do domínio permitido "
                                        f"{col_spec.allowed_values} na coluna '{col_name}' (linha {idx}, PK={pk_val})."
                                    ),
                                )
                            )

                    if compiled_regex and isinstance(coerced_val, str):
                        if not compiled_regex.match(coerced_val):
                            row_range_failed = True
                            anomalies.append(
                                AnomalyRecord(
                                    violation_id=next_violation_id(),
                                    rule_category="RANGE_CHECK",
                                    rule_name="regex_pattern_check",
                                    severity=col_spec.severity,
                                    column_name=col_name,
                                    row_index=idx,
                                    record_pk=pk_val,
                                    observed_value=coerced_val,
                                    expected_constraint=f"MATCHES /{col_spec.regex_pattern}/",
                                    diagnostic_message=(
                                        f"Valor '{coerced_val}' não atende ao padrão regex "
                                        f"'{col_spec.regex_pattern}' na coluna '{col_name}' (linha {idx}, PK={pk_val})."
                                    ),
                                )
                            )

                    if row_range_failed:
                        range_failures += 1
                        corrupted_row_indices.add(idx)

            # Consolida resumos estatísticos das regras avaliadas para a coluna
            if not col_spec.nullable or col_spec.is_primary_key:
                rule_summaries.append(
                    RuleExecutionSummary(
                        rule_category="NULLABILITY",
                        rule_name="not_null_check",
                        column_name=col_name,
                        severity=col_spec.severity,
                        total_evaluated=dataset.row_count,
                        failed_count=null_failures,
                        passed=null_failures == 0,
                    )
                )

            rule_summaries.append(
                RuleExecutionSummary(
                    rule_category="DATA_TYPE",
                    rule_name=f"type_check_{col_spec.expected_type.value.lower()}",
                    column_name=col_name,
                    severity=col_spec.severity,
                    total_evaluated=non_null_evaluated,
                    failed_count=type_failures,
                    passed=type_failures == 0,
                )
            )

            if col_spec.unique or col_spec.is_primary_key:
                rule_summaries.append(
                    RuleExecutionSummary(
                        rule_category="UNIQUENESS",
                        rule_name="unique_id_check",
                        column_name=col_name,
                        severity=col_spec.severity,
                        total_evaluated=non_null_evaluated - type_failures,
                        failed_count=unique_failures,
                        passed=unique_failures == 0,
                    )
                )

            if has_range_or_domain_rules:
                rule_summaries.append(
                    RuleExecutionSummary(
                        rule_category="RANGE_CHECK",
                        rule_name="domain_and_range_bounds",
                        column_name=col_name,
                        severity=col_spec.severity,
                        total_evaluated=range_evaluated,
                        failed_count=range_failures,
                        passed=range_failures == 0,
                    )
                )

        elapsed_ms = round((time.perf_counter_ns() - start_ns) / 1_000_000.0, 2)
        corrupted_count = len(corrupted_row_indices)
        healthy_count = max(0, dataset.row_count - corrupted_count)

        return ValidationReport(
            run_id=run_id,
            evaluated_at_utc=now_utc,
            contract=contract,
            source_identifier=dataset.source_name,
            total_rows=dataset.row_count,
            total_columns=dataset.column_count,
            healthy_rows_count=healthy_count,
            corrupted_rows_count=corrupted_count,
            rule_summaries=rule_summaries,
            anomalies=anomalies,
            execution_time_ms=elapsed_ms,
        )
