"""
Conectores Modulares de Fontes de Dados (CSV, Apache Parquet e SQLite).

Converte qualquer fonte suportada para uma representação canônica em memória
(`TabularDataset` contendo `columns: List[str]` e `rows: List[Dict[str, Any]]`)
para inspeção agnóstica pelo motor de Data Quality em Python puro.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TabularDataset:
    """Representação canônica em Python puro de um conjunto de dados tabular."""

    source_name: str
    source_format: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    physical_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.columns)


class BaseDataConnector(ABC):
    """Interface abstrata para conectores de leitura de dados."""

    @abstractmethod
    def load(self) -> TabularDataset:
        """Carrega os registros e metadados estruturais da fonte de dados."""


class CSVDataConnector(BaseDataConnector):
    """Conector de leitura para arquivos CSV em Python puro."""

    def __init__(
        self,
        file_path: Path,
        delimiter: str = ",",
        encoding: str = "utf-8",
    ) -> None:
        self.file_path = Path(file_path)
        self.delimiter = delimiter
        self.encoding = encoding

    def load(self) -> TabularDataset:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Arquivo CSV não encontrado: {self.file_path}")

        with open(self.file_path, "r", encoding=self.encoding, newline="") as fh:
            reader = csv.DictReader(fh, delimiter=self.delimiter)
            columns = list(reader.fieldnames or [])
            rows: List[Dict[str, Any]] = [dict(row) for row in reader]

        return TabularDataset(
            source_name=str(self.file_path.name),
            source_format="CSV",
            columns=columns,
            rows=rows,
            physical_metadata={
                "path": str(self.file_path),
                "size_bytes": self.file_path.stat().st_size,
                "delimiter": self.delimiter,
                "encoding": self.encoding,
            },
        )


class ParquetDataConnector(BaseDataConnector):
    """
    Conector para arquivos colunares Apache Parquet (.parquet).
    Utiliza PyArrow para decodificação física colunar quando disponível,
    com fallback para container JSON-Parquet caso executado sem bibliotecas C++.
    """

    def __init__(self, file_path: Path) -> None:
        self.file_path = Path(file_path)

    def load(self) -> TabularDataset:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Arquivo Parquet não encontrado: {self.file_path}")

        try:
            import pyarrow.parquet as pq  # type: ignore

            table = pq.read_table(self.file_path)
            columns = list(table.schema.names)
            rows = table.to_pylist()
            schema_info = {field.name: str(field.type) for field in table.schema}
            engine_used = "pyarrow"
        except Exception:
            # Fallback em Python puro caso o arquivo tenha sido persistido via fallback JSON-colunar
            with open(self.file_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            columns = list(payload["columns"])
            rows = list(payload["rows"])
            schema_info = payload.get("schema", {})
            engine_used = "pure-python-fallback"

        return TabularDataset(
            source_name=str(self.file_path.name),
            source_format="PARQUET",
            columns=columns,
            rows=rows,
            physical_metadata={
                "path": str(self.file_path),
                "size_bytes": self.file_path.stat().st_size,
                "parquet_engine": engine_used,
                "physical_schema": schema_info,
            },
        )


class SQLiteDataConnector(BaseDataConnector):
    """Conector em Python puro para tabelas ou queries em bancos relacionais SQLite."""

    def __init__(
        self,
        db_path: Path,
        table_name: str,
        custom_query: Optional[str] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.table_name = table_name
        self.custom_query = custom_query

    def load(self) -> TabularDataset:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Banco de dados SQLite não encontrado: {self.db_path}")

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            pragma_rows = conn.execute(f"PRAGMA table_info({self.table_name})").fetchall()
            declared_types = {str(r["name"]): str(r["type"]) for r in pragma_rows}

            sql = self.custom_query or f"SELECT * FROM {self.table_name}"
            cursor = conn.execute(sql)
            columns = [desc[0] for desc in (cursor.description or [])]
            rows = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

        return TabularDataset(
            source_name=f"{self.db_path.name}::{self.table_name}",
            source_format="SQLITE",
            columns=columns,
            rows=rows,
            physical_metadata={
                "db_path": str(self.db_path),
                "table_name": self.table_name,
                "declared_sqlite_types": declared_types,
            },
        )
