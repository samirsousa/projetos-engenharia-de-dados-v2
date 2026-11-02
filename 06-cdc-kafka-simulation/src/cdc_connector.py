"""
Componente 2: Conector CDC (Simulador Debezium / Log Reader).

Monitora a tabela interna de Write-Ahead Log (`_cdc_wal_log`) do SQLite a partir do
último Log Sequence Number (LSN) processado (checkpoint), serializa cada mutação
no envelope canônico do Debezium (`before`, `after`, `source`, `op`, `ts_ms`) e
grava arquivos JSON de micro-lote de forma atômica no diretório de logs (Camada Bronze).
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import PipelineConfig, setup_logger
from src.database import get_connection, init_oltp_database

logger = setup_logger("CDC-Connector")


@dataclass
class ConnectorCheckpoint:
    """Estrutura de controle de offset (LSN) do conector CDC."""

    connector_name: str = "sqlite-debezium-cdc-connector"
    last_lsn: int = 0
    batches_emitted: int = 0
    total_events_emitted: int = 0
    updated_at_utc: str = ""


class DebeziumCDCConnector:
    """
    Simulador de conector CDC Log-Based inspirado no Apache Kafka Connect / Debezium.

    Garantias arquiteturais:
    - Leitura ordenada por LSN (Log Sequence Number) monotônico.
    - Escrita atômica de arquivos de log JSON via arquivo temporário `.tmp` + `os.replace`.
    - Persistência de offset (checkpoint) somente após flush em disco (At-Least-Once Delivery).
    """

    def __init__(self, config: Optional[PipelineConfig] = None, batch_size: int = 100) -> None:
        self.config = config or PipelineConfig()
        self.config.ensure_directories()
        init_oltp_database(self.config.oltp_db_path)
        self.batch_size = batch_size

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def load_checkpoint(self) -> ConnectorCheckpoint:
        """Carrega o último LSN salvo no arquivo de offset ou inicia do LSN 0."""
        offset_file = self.config.connector_offset_path
        if not offset_file.exists():
            return ConnectorCheckpoint(updated_at_utc=self._utc_now().isoformat())

        with open(offset_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return ConnectorCheckpoint(
            connector_name=data.get("connector_name", "sqlite-debezium-cdc-connector"),
            last_lsn=int(data.get("last_lsn", 0)),
            batches_emitted=int(data.get("batches_emitted", 0)),
            total_events_emitted=int(data.get("total_events_emitted", 0)),
            updated_at_utc=str(data.get("updated_at_utc", "")),
        )

    def save_checkpoint(self, checkpoint: ConnectorCheckpoint) -> None:
        """Persiste o offset de forma atômica no sistema de arquivos."""
        offset_file = self.config.connector_offset_path
        tmp_file = offset_file.with_suffix(".json.tmp")
        payload = {
            "connector_name": checkpoint.connector_name,
            "last_lsn": checkpoint.last_lsn,
            "batches_emitted": checkpoint.batches_emitted,
            "total_events_emitted": checkpoint.total_events_emitted,
            "updated_at_utc": checkpoint.updated_at_utc,
        }
        with open(tmp_file, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_file, offset_file)

    @staticmethod
    def _build_debezium_envelope(row: Dict[str, Any]) -> Dict[str, Any]:
        """Constrói o envelope JSON padrão Debezium para um evento de alteração."""
        before_state = json.loads(row["before_json"]) if row["before_json"] else None
        after_state = json.loads(row["after_json"]) if row["after_json"] else None
        connector_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        return {
            "schema": {
                "type": "struct",
                "name": f"cdc_pipeline.{row['schema_name']}.{row['table_name']}.Envelope",
                "version": 1,
            },
            "payload": {
                "lsn": int(row["lsn"]),
                "tx_id": str(row["tx_id"]),
                "op": str(row["op"]),
                "op_type": str(row["op_type"]),
                "record_pk": str(row["record_pk"]),
                "before": before_state,
                "after": after_state,
                "source": {
                    "version": "1.0.0-debezium-sim",
                    "connector": "sqlite-wal-cdc",
                    "name": "oltp_ecommerce_server",
                    "ts_ms": int(row["ts_ms"]),
                    "event_time_utc": str(row["event_time_utc"]),
                    "db": "oltp_source",
                    "schema": str(row["schema_name"]),
                    "table": str(row["table_name"]),
                    "lsn": int(row["lsn"]),
                    "tx_id": str(row["tx_id"]),
                },
                "ts_ms": connector_ts_ms,
            },
        }

    def fetch_pending_changes(self, after_lsn: int) -> List[Dict[str, Any]]:
        """Busca eventos no log transacional com LSN estritamente maior que `after_lsn`."""
        with get_connection(self.config.oltp_db_path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    lsn, tx_id, op, op_type, schema_name, table_name,
                    record_pk, before_json, after_json, ts_ms, event_time_utc
                  FROM _cdc_wal_log
                 WHERE lsn > ?
                 ORDER BY lsn ASC
                 LIMIT ?
                """,
                (after_lsn, self.batch_size),
            )
            return [dict(r) for r in cursor.fetchall()]

    def poll_and_emit(self) -> Optional[Path]:
        """
        Executa um ciclo de leitura do WAL, gera o arquivo JSON de log e atualiza o offset.

        Returns:
            Path do arquivo de lote JSON gerado, ou None se não houver novas alterações.
        """
        checkpoint = self.load_checkpoint()
        raw_rows = self.fetch_pending_changes(after_lsn=checkpoint.last_lsn)

        if not raw_rows:
            logger.debug("Nenhuma nova alteração no WAL após LSN=%d.", checkpoint.last_lsn)
            return None

        envelopes = [self._build_debezium_envelope(r) for r in raw_rows]
        min_lsn = int(raw_rows[0]["lsn"])
        max_lsn = int(raw_rows[-1]["lsn"])
        now_utc = self._utc_now()
        timestamp_slug = now_utc.strftime("%Y%m%d_%H%M%S_%f")

        batch_filename = f"cdc_events_lsn_{min_lsn:06d}_{max_lsn:06d}_{timestamp_slug}.json"
        batch_path = self.config.cdc_logs_dir / batch_filename
        tmp_batch_path = batch_path.with_suffix(".json.tmp")

        op_counts = {"INSERT": 0, "UPDATE": 0, "DELETE": 0}
        for row in raw_rows:
            op_type = str(row["op_type"])
            op_counts[op_type] = op_counts.get(op_type, 0) + 1

        batch_document = {
            "batch_metadata": {
                "batch_id": batch_filename.replace(".json", ""),
                "connector": checkpoint.connector_name,
                "emitted_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "min_lsn": min_lsn,
                "max_lsn": max_lsn,
                "event_count": len(envelopes),
                "operation_breakdown": op_counts,
            },
            "events": envelopes,
        }

        # Escrita atômica: garante que o consumidor nunca leia um arquivo pela metade
        with open(tmp_batch_path, "w", encoding="utf-8") as fh:
            json.dump(batch_document, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_batch_path, batch_path)

        # Atualiza e persiste o offset do conector
        checkpoint.last_lsn = max_lsn
        checkpoint.batches_emitted += 1
        checkpoint.total_events_emitted += len(envelopes)
        checkpoint.updated_at_utc = now_utc.isoformat()
        self.save_checkpoint(checkpoint)

        logger.info(
            "Batch CDC emitido | arquivo=%s | LSN=[%d..%d] | total=%d (I=%d, U=%d, D=%d)",
            batch_filename,
            min_lsn,
            max_lsn,
            len(envelopes),
            op_counts.get("INSERT", 0),
            op_counts.get("UPDATE", 0),
            op_counts.get("DELETE", 0),
        )
        return batch_path

    def drain_all_pending(self) -> List[Path]:
        """Drena todos os eventos pendentes no WAL em lotes sucessivos até esgotar."""
        emitted_files: List[Path] = []
        while True:
            batch_file = self.poll_and_emit()
            if batch_file is None:
                break
            emitted_files.append(batch_file)
        if not emitted_files:
            logger.info("WAL sincronizado. Nenhum evento pendente para captura.")
        return emitted_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Conector CDC (Debezium Simulator) para leitura do WAL SQLite e emissão de logs JSON."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Quantidade máxima de eventos por arquivo de lote JSON (padrão: 100).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Intervalo de polling em segundos no modo contínuo (padrão: 2.0s).",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Executa continuamente monitorando novas transações (daemon streaming).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    connector = DebeziumCDCConnector(batch_size=args.batch_size)

    if args.continuous:
        logger.info(
            "Conector CDC iniciado em modo streaming contínuo (poll_interval=%.1fs)...",
            args.poll_interval,
        )
        try:
            while True:
                connector.drain_all_pending()
                time.sleep(args.poll_interval)
        except KeyboardInterrupt:
            logger.info("Conector CDC encerrado pelo usuário.")
    else:
        connector.drain_all_pending()


if __name__ == "__main__":
    main()
