"""
Componente 3: Consumidor Batch da Camada Silver e Gerador de Relatório Diário de Auditoria.

Lê os lotes JSON gerados pelo conector CDC na Camada Bronze, aplica as mutações
(INSERT, UPDATE, DELETE) de forma idempotente na tabela espelho `silver_orders`
(Camada Silver), executa a reconciliação criptográfica de estado entre OLTP e Silver
e gera o Relatório Diário de Auditoria de Dados em Markdown e JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import PipelineConfig, setup_logger
from src.database import get_connection, init_oltp_database, init_silver_database

logger = setup_logger("Silver-Consumer")


@dataclass
class BatchIngestionMetrics:
    """Métricas coletadas durante a execução do consumidor Silver."""

    batches_processed: int = 0
    events_read: int = 0
    events_applied: int = 0
    events_skipped_duplicate: int = 0
    events_skipped_stale: int = 0
    inserts_applied: int = 0
    updates_applied: int = 0
    deletes_applied: int = 0
    processed_files: List[str] = field(default_factory=list)


class SilverCDCConsumer:
    """
    Motor de ingestão CDC para a Camada Silver com garantia de idempotência por LSN
    e auditoria completa de qualidade/reconciliação de dados.
    """

    def __init__(self, config: Optional[PipelineConfig] = None, archive_processed: bool = True) -> None:
        self.config = config or PipelineConfig()
        self.config.ensure_directories()
        init_oltp_database(self.config.oltp_db_path)
        init_silver_database(self.config.silver_db_path)
        self.archive_processed = archive_processed

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _compute_field_diff(
        before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Calcula exatamente quais colunas mudaram entre `before` e `after`."""
        if not before or not after:
            return {}
        diffs: Dict[str, Dict[str, Any]] = {}
        for key, after_val in after.items():
            if key == "updated_at":
                continue
            before_val = before.get(key)
            if before_val != after_val:
                diffs[key] = {"before": before_val, "after": after_val}
        return diffs

    @staticmethod
    def _compute_amount_delta(
        op: str, before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]
    ) -> float:
        """Calcula o impacto financeiro líquido da operação CDC."""
        before_amt = float(before.get("total_amount", 0.0)) if before else 0.0
        after_amt = float(after.get("total_amount", 0.0)) if after else 0.0
        if op in ("c", "r"):
            return round(after_amt, 2)
        if op == "u":
            return round(after_amt - before_amt, 2)
        if op == "d":
            return round(-before_amt, 2)
        return 0.0

    def discover_pending_batches(self) -> List[Path]:
        """Lista os arquivos JSON de lote CDC na camada Bronze ordenados por LSN/nome."""
        files = sorted(self.config.cdc_logs_dir.glob("cdc_events_lsn_*.json"))
        return [f for f in files if f.is_file()]

    def process_all_batches(self) -> BatchIngestionMetrics:
        """Processa todos os lotes JSON pendentes e aplica na tabela espelho `silver_orders`."""
        metrics = BatchIngestionMetrics()
        pending_files = self.discover_pending_batches()

        if not pending_files:
            logger.info("Nenhum arquivo de lote JSON pendente em %s.", self.config.cdc_logs_dir)
            return metrics

        logger.info("Encontrados %d arquivo(s) de lote CDC para processamento.", len(pending_files))

        for batch_path in pending_files:
            self._process_single_batch(batch_path, metrics)

        logger.info(
            "Ingestão Silver concluída | lotes=%d | lidos=%d | aplicados=%d (I=%d, U=%d, D=%d) | ignorados=%d",
            metrics.batches_processed,
            metrics.events_read,
            metrics.events_applied,
            metrics.inserts_applied,
            metrics.updates_applied,
            metrics.deletes_applied,
            metrics.events_skipped_duplicate + metrics.events_skipped_stale,
        )
        return metrics

    def _process_single_batch(self, batch_path: Path, metrics: BatchIngestionMetrics) -> None:
        batch_filename = batch_path.name
        file_hash = self._file_sha256(batch_path)

        with open(batch_path, "r", encoding="utf-8") as fh:
            batch_doc = json.load(fh)

        events: List[Dict[str, Any]] = batch_doc.get("events", [])
        now_utc = self._utc_now()
        now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        now_ms = int(now_utc.timestamp() * 1000)

        with get_connection(self.config.silver_db_path) as conn:
            # 1. Verifica idempotência em nível de arquivo de lote
            already_done = conn.execute(
                "SELECT 1 FROM silver_processed_batches WHERE batch_filename = ? OR file_sha256 = ?",
                (batch_filename, file_hash),
            ).fetchone()

            if already_done:
                logger.warning(
                    "Lote %s já foi processado anteriormente (idempotência de lote). Arquivando...",
                    batch_filename,
                )
                if self.archive_processed:
                    shutil.move(str(batch_path), str(self.config.cdc_archive_dir / batch_filename))
                return

            batch_applied = 0
            batch_skipped = 0
            lsns_in_batch: List[int] = []

            for envelope in events:
                metrics.events_read += 1
                payload = envelope["payload"]
                lsn = int(payload["lsn"])
                tx_id = str(payload["tx_id"])
                op = str(payload["op"])
                op_type = str(payload["op_type"])
                record_pk = str(payload["record_pk"])
                before = payload.get("before")
                after = payload.get("after")
                source = payload.get("source", {})
                source_ts_ms = int(source.get("ts_ms", payload.get("ts_ms", now_ms)))
                source_event_time = str(source.get("event_time_utc", now_iso))
                source_event_date = source_event_time[:10]
                table_name = str(source.get("table", "orders"))

                lsns_in_batch.append(lsn)
                replication_lag_ms = max(0, now_ms - source_ts_ms)
                diff_dict = self._compute_field_diff(before, after)
                amount_delta = self._compute_amount_delta(op, before, after)

                # 2. Verifica se este LSN já foi registrado no audit log
                existing_audit = conn.execute(
                    "SELECT 1 FROM silver_cdc_audit_log WHERE lsn = ?",
                    (lsn,),
                ).fetchone()
                if existing_audit:
                    metrics.events_skipped_duplicate += 1
                    batch_skipped += 1
                    continue

                # 3. Verifica versão / LSN atual do registro na tabela espelho Silver
                current_row = conn.execute(
                    "SELECT _cdc_last_lsn, _record_version FROM silver_orders WHERE order_id = ?",
                    (record_pk,),
                ).fetchone()

                if current_row and int(current_row["_cdc_last_lsn"]) >= lsn:
                    # Evento atrasado / fora de ordem (LSN menor ou igual ao estado já consolidado)
                    conn.execute(
                        """
                        INSERT INTO silver_cdc_audit_log (
                            batch_file, lsn, tx_id, op, op_type, table_name, record_pk,
                            before_state_json, after_state_json, changed_fields_json,
                            amount_delta, source_ts_ms, source_event_date,
                            applied_at_utc, replication_lag_ms, apply_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SKIPPED_STALE_LSN')
                        """,
                        (
                            batch_filename,
                            lsn,
                            tx_id,
                            op,
                            op_type,
                            table_name,
                            record_pk,
                            json.dumps(before, ensure_ascii=False) if before else None,
                            json.dumps(after, ensure_ascii=False) if after else None,
                            json.dumps(diff_dict, ensure_ascii=False) if diff_dict else None,
                            0.0,
                            source_ts_ms,
                            source_event_date,
                            now_iso,
                            replication_lag_ms,
                        ),
                    )
                    metrics.events_skipped_stale += 1
                    batch_skipped += 1
                    continue

                # 4. Aplica mutação na tabela espelho `silver_orders`
                next_version = (int(current_row["_record_version"]) + 1) if current_row else 1

                if op in ("c", "r", "u"):
                    if not after:
                        raise ValueError(f"Evento LSN={lsn} ({op_type}) não possui estado 'after'.")
                    conn.execute(
                        """
                        INSERT INTO silver_orders (
                            order_id, customer_id, customer_name, product_sku, category,
                            quantity, unit_price, total_amount, status, payment_method,
                            region, created_at, updated_at,
                            _cdc_last_lsn, _cdc_last_op, _cdc_tx_id, _cdc_source_ts_ms,
                            _cdc_ingested_at, _is_deleted, _deleted_at, _record_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
                        ON CONFLICT(order_id) DO UPDATE SET
                            customer_id       = excluded.customer_id,
                            customer_name     = excluded.customer_name,
                            product_sku       = excluded.product_sku,
                            category          = excluded.category,
                            quantity          = excluded.quantity,
                            unit_price        = excluded.unit_price,
                            total_amount      = excluded.total_amount,
                            status            = excluded.status,
                            payment_method    = excluded.payment_method,
                            region            = excluded.region,
                            created_at        = excluded.created_at,
                            updated_at        = excluded.updated_at,
                            _cdc_last_lsn     = excluded._cdc_last_lsn,
                            _cdc_last_op      = excluded._cdc_last_op,
                            _cdc_tx_id        = excluded._cdc_tx_id,
                            _cdc_source_ts_ms = excluded._cdc_source_ts_ms,
                            _cdc_ingested_at  = excluded._cdc_ingested_at,
                            _is_deleted       = 0,
                            _deleted_at       = NULL,
                            _record_version   = ?
                        """,
                        (
                            after["order_id"],
                            after["customer_id"],
                            after["customer_name"],
                            after["product_sku"],
                            after["category"],
                            int(after["quantity"]),
                            float(after["unit_price"]),
                            float(after["total_amount"]),
                            after["status"],
                            after["payment_method"],
                            after["region"],
                            after["created_at"],
                            after["updated_at"],
                            lsn,
                            op,
                            tx_id,
                            source_ts_ms,
                            now_iso,
                            next_version,
                            next_version,
                        ),
                    )
                    if op in ("c", "r"):
                        metrics.inserts_applied += 1
                    else:
                        metrics.updates_applied += 1

                elif op == "d":
                    # Soft-Delete governado (Tombstone) mantendo histórico na Silver
                    if current_row:
                        conn.execute(
                            """
                            UPDATE silver_orders
                               SET _cdc_last_lsn     = ?,
                                   _cdc_last_op      = 'd',
                                   _cdc_tx_id        = ?,
                                   _cdc_source_ts_ms = ?,
                                   _cdc_ingested_at  = ?,
                                   _is_deleted       = 1,
                                   _deleted_at       = ?,
                                   _record_version   = ?
                             WHERE order_id = ?
                            """,
                            (
                                lsn,
                                tx_id,
                                source_ts_ms,
                                now_iso,
                                now_iso,
                                next_version,
                                record_pk,
                            ),
                        )
                    elif before:
                        # Caso um DELETE chegue para um registro ainda não materializado, cria tombstone
                        conn.execute(
                            """
                            INSERT INTO silver_orders (
                                order_id, customer_id, customer_name, product_sku, category,
                                quantity, unit_price, total_amount, status, payment_method,
                                region, created_at, updated_at,
                                _cdc_last_lsn, _cdc_last_op, _cdc_tx_id, _cdc_source_ts_ms,
                                _cdc_ingested_at, _is_deleted, _deleted_at, _record_version
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'd', ?, ?, ?, 1, ?, 1)
                            """,
                            (
                                before["order_id"],
                                before["customer_id"],
                                before["customer_name"],
                                before["product_sku"],
                                before["category"],
                                int(before["quantity"]),
                                float(before["unit_price"]),
                                float(before["total_amount"]),
                                before["status"],
                                before["payment_method"],
                                before["region"],
                                before["created_at"],
                                before["updated_at"],
                                lsn,
                                tx_id,
                                source_ts_ms,
                                now_iso,
                                now_iso,
                            ),
                        )
                    metrics.deletes_applied += 1

                # 5. Registra na trilha imutável de auditoria
                conn.execute(
                    """
                    INSERT INTO silver_cdc_audit_log (
                        batch_file, lsn, tx_id, op, op_type, table_name, record_pk,
                        before_state_json, after_state_json, changed_fields_json,
                        amount_delta, source_ts_ms, source_event_date,
                        applied_at_utc, replication_lag_ms, apply_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'APPLIED')
                    """,
                    (
                        batch_filename,
                        lsn,
                        tx_id,
                        op,
                        op_type,
                        table_name,
                        record_pk,
                        json.dumps(before, ensure_ascii=False) if before else None,
                        json.dumps(after, ensure_ascii=False) if after else None,
                        json.dumps(diff_dict, ensure_ascii=False) if diff_dict else None,
                        amount_delta,
                        source_ts_ms,
                        source_event_date,
                        now_iso,
                        replication_lag_ms,
                    ),
                )
                batch_applied += 1
                metrics.events_applied += 1

            # 6. Marca o lote como processado
            conn.execute(
                """
                INSERT INTO silver_processed_batches (
                    batch_filename, file_sha256, events_total, events_applied,
                    events_skipped, min_lsn, max_lsn, processed_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_filename,
                    file_hash,
                    len(events),
                    batch_applied,
                    batch_skipped,
                    min(lsns_in_batch) if lsns_in_batch else None,
                    max(lsns_in_batch) if lsns_in_batch else None,
                    now_iso,
                ),
            )

        metrics.batches_processed += 1
        metrics.processed_files.append(batch_filename)

        if self.archive_processed:
            dest_path = self.config.cdc_archive_dir / batch_filename
            shutil.move(str(batch_path), str(dest_path))

        logger.info(
            "Lote aplicado na Silver | arquivo=%s | aplicados=%d | ignorados=%d",
            batch_filename,
            batch_applied,
            batch_skipped,
        )

    @staticmethod
    def _hash_records(rows: List[Dict[str, Any]]) -> str:
        """Gera hash SHA-256 determinístico de um conjunto de registros para prova de paridade."""
        canonical_lines: List[str] = []
        business_cols = [
            "order_id",
            "customer_id",
            "customer_name",
            "product_sku",
            "category",
            "quantity",
            "unit_price",
            "total_amount",
            "status",
            "payment_method",
            "region",
            "created_at",
            "updated_at",
        ]
        for row in sorted(rows, key=lambda r: str(r["order_id"])):
            normalized = {
                col: (round(float(row[col]), 2) if col in ("unit_price", "total_amount") else row[col])
                for col in business_cols
            }
            canonical_lines.append(json.dumps(normalized, sort_keys=True, ensure_ascii=False))
        digest = hashlib.sha256("\n".join(canonical_lines).encode("utf-8")).hexdigest()
        return digest

    def reconcile_oltp_vs_silver(self) -> Dict[str, Any]:
        """
        Compara todos os registros ativos do banco OLTP com a view ativa da Camada Silver,
        validando contagem de linhas, soma financeira (GMV) e hash criptográfico SHA-256.
        """
        with get_connection(self.config.oltp_db_path) as oltp_conn:
            oltp_rows = [
                dict(r)
                for r in oltp_conn.execute("SELECT * FROM orders ORDER BY order_id ASC").fetchall()
            ]

        with get_connection(self.config.silver_db_path) as silver_conn:
            silver_active_rows = [
                dict(r)
                for r in silver_conn.execute(
                    "SELECT * FROM vw_silver_orders_active ORDER BY order_id ASC"
                ).fetchall()
            ]
            tombstone_count = int(
                silver_conn.execute(
                    "SELECT COUNT(*) AS cnt FROM silver_orders WHERE _is_deleted = 1"
                ).fetchone()["cnt"]
            )

        oltp_count = len(oltp_rows)
        silver_active_count = len(silver_active_rows)
        oltp_gmv = round(sum(float(r["total_amount"]) for r in oltp_rows), 2)
        silver_gmv = round(sum(float(r["total_amount"]) for r in silver_active_rows), 2)

        oltp_hash = self._hash_records(oltp_rows)
        silver_hash = self._hash_records(silver_active_rows)

        oltp_ids = {str(r["order_id"]) for r in oltp_rows}
        silver_ids = {str(r["order_id"]) for r in silver_active_rows}
        missing_in_silver = sorted(oltp_ids - silver_ids)
        extra_in_silver = sorted(silver_ids - oltp_ids)

        is_consistent = (
            oltp_count == silver_active_count
            and abs(oltp_gmv - silver_gmv) < 0.01
            and oltp_hash == silver_hash
        )

        return {
            "is_consistent": is_consistent,
            "status_label": "CONVERGENTE (100% PARIDADE)" if is_consistent else "DIVERGÊNCIA DETECTADA",
            "oltp_active_rows": oltp_count,
            "silver_active_rows": silver_active_count,
            "silver_tombstone_rows": tombstone_count,
            "oltp_total_gmv": oltp_gmv,
            "silver_total_gmv": silver_gmv,
            "gmv_drift": round(silver_gmv - oltp_gmv, 2),
            "oltp_sha256": oltp_hash,
            "silver_sha256": silver_hash,
            "missing_in_silver": missing_in_silver,
            "extra_in_silver": extra_in_silver,
        }

    def generate_daily_audit_report(
        self, report_date: Optional[str] = None
    ) -> Tuple[Path, Path, Dict[str, Any]]:
        """
        Gera o Relatório Diário de Auditoria de Dados da Camada Silver em Markdown e JSON.

        Args:
            report_date: Data alvo no formato YYYY-MM-DD (padrão: data UTC atual).

        Returns:
            Tupla (caminho_markdown, caminho_json, dicionario_dados_auditoria).
        """
        target_date = report_date or self._utc_now().strftime("%Y-%m-%d")
        generated_at_iso = self._utc_now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        reconciliation = self.reconcile_oltp_vs_silver()

        with get_connection(self.config.silver_db_path) as conn:
            # 1. Métricas agregadas de eventos CDC na data
            op_summary_rows = conn.execute(
                """
                SELECT
                    op_type,
                    apply_status,
                    COUNT(*) AS event_count,
                    ROUND(SUM(amount_delta), 2) AS net_amount_delta,
                    ROUND(AVG(replication_lag_ms), 2) AS avg_lag_ms,
                    MAX(replication_lag_ms) AS max_lag_ms,
                    MIN(lsn) AS min_lsn,
                    MAX(lsn) AS max_lsn
                  FROM silver_cdc_audit_log
                 WHERE source_event_date = ?
                 GROUP BY op_type, apply_status
                 ORDER BY op_type
                """,
                (target_date,),
            ).fetchall()

            # 2. Métricas globais acumuladas na auditoria
            overall_audit = dict(
                conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total_events,
                        SUM(CASE WHEN op_type = 'INSERT' AND apply_status = 'APPLIED' THEN 1 ELSE 0 END) AS total_inserts,
                        SUM(CASE WHEN op_type = 'UPDATE' AND apply_status = 'APPLIED' THEN 1 ELSE 0 END) AS total_updates,
                        SUM(CASE WHEN op_type = 'DELETE' AND apply_status = 'APPLIED' THEN 1 ELSE 0 END) AS total_deletes,
                        SUM(CASE WHEN apply_status != 'APPLIED' THEN 1 ELSE 0 END) AS total_skipped,
                        ROUND(SUM(CASE WHEN op_type = 'INSERT' AND apply_status = 'APPLIED' THEN amount_delta ELSE 0 END), 2) AS gross_inserted_value,
                        ROUND(SUM(CASE WHEN op_type = 'UPDATE' AND apply_status = 'APPLIED' THEN amount_delta ELSE 0 END), 2) AS net_updated_value,
                        ROUND(SUM(CASE WHEN op_type = 'DELETE' AND apply_status = 'APPLIED' THEN ABS(amount_delta) ELSE 0 END), 2) AS gross_deleted_value,
                        ROUND(AVG(replication_lag_ms), 2) AS avg_lag_ms,
                        MAX(replication_lag_ms) AS max_lag_ms,
                        MIN(lsn) AS min_lsn,
                        MAX(lsn) AS max_lsn
                      FROM silver_cdc_audit_log
                     WHERE source_event_date = ?
                    """,
                    (target_date,),
                ).fetchone()
            )

            # 3. Distribuição de pedidos na Silver por Status
            status_distribution = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT
                        status,
                        COUNT(*) AS order_count,
                        ROUND(SUM(total_amount), 2) AS total_gmv
                      FROM silver_orders
                     WHERE _is_deleted = 0
                     GROUP BY status
                     ORDER BY total_gmv DESC
                    """
                ).fetchall()
            ]

            # 4. Distribuição Regional na Silver
            region_distribution = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT
                        region,
                        COUNT(*) AS order_count,
                        ROUND(SUM(total_amount), 2) AS total_gmv
                      FROM silver_orders
                     WHERE _is_deleted = 0
                     GROUP BY region
                     ORDER BY total_gmv DESC
                    """
                ).fetchall()
            ]

            # 5. Lotes processados
            batches_info = dict(
                conn.execute(
                    """
                    SELECT
                        COUNT(*) AS batches_count,
                        COALESCE(SUM(events_total), 0) AS total_batch_events
                      FROM silver_processed_batches
                     WHERE substr(processed_at_utc, 1, 10) = ?
                    """,
                    (target_date,),
                ).fetchone()
            )

            # 6. Anomalias / Eventos de Governança Relevantes (ex: High-value deletes > R$ 3.000 ou multi-updates)
            high_value_deletes = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT lsn, tx_id, record_pk, ABS(amount_delta) AS removed_value, applied_at_utc
                      FROM silver_cdc_audit_log
                     WHERE source_event_date = ?
                       AND op_type = 'DELETE'
                       AND ABS(amount_delta) >= 3000.0
                     ORDER BY ABS(amount_delta) DESC
                     LIMIT 10
                    """,
                    (target_date,),
                ).fetchall()
            ]

            # 7. Amostra das últimas 10 mutações aplicadas para trilha de auditoria
            recent_mutations = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT
                        lsn, tx_id, op_type, record_pk, changed_fields_json,
                        amount_delta, replication_lag_ms, applied_at_utc
                      FROM silver_cdc_audit_log
                     WHERE source_event_date = ?
                     ORDER BY lsn DESC
                     LIMIT 10
                    """,
                    (target_date,),
                ).fetchall()
            ]

        audit_payload: Dict[str, Any] = {
            "report_metadata": {
                "report_date": target_date,
                "generated_at_utc": generated_at_iso,
                "pipeline": "SQLite-Debezium-Silver-CDC",
                "version": "1.0.0",
            },
            "reconciliation": reconciliation,
            "daily_cdc_summary": {
                "batches_processed": int(batches_info.get("batches_count") or 0),
                "total_events": int(overall_audit.get("total_events") or 0),
                "inserts": int(overall_audit.get("total_inserts") or 0),
                "updates": int(overall_audit.get("total_updates") or 0),
                "deletes": int(overall_audit.get("total_deletes") or 0),
                "skipped_events": int(overall_audit.get("total_skipped") or 0),
                "min_lsn": overall_audit.get("min_lsn"),
                "max_lsn": overall_audit.get("max_lsn"),
                "avg_replication_lag_ms": float(overall_audit.get("avg_lag_ms") or 0.0),
                "max_replication_lag_ms": int(overall_audit.get("max_lag_ms") or 0),
                "gross_inserted_value_brl": float(overall_audit.get("gross_inserted_value") or 0.0),
                "net_updated_value_brl": float(overall_audit.get("net_updated_value") or 0.0),
                "gross_deleted_value_brl": float(overall_audit.get("gross_deleted_value") or 0.0),
            },
            "operation_breakdown": [dict(r) for r in op_summary_rows],
            "silver_active_status_distribution": status_distribution,
            "silver_active_region_distribution": region_distribution,
            "governance_alerts": {
                "high_value_deletes_count": len(high_value_deletes),
                "high_value_deletes": high_value_deletes,
            },
            "recent_mutations_sample": recent_mutations,
        }

        md_path = self.config.reports_dir / f"audit_report_{target_date}.md"
        json_path = self.config.reports_dir / f"audit_report_{target_date}.json"

        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(audit_payload, fh, indent=2, ensure_ascii=False)

        md_content = self._render_markdown_report(audit_payload)
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(md_content)

        logger.info(
            "Relatório Diário de Auditoria gerado | MD=%s | JSON=%s | Status=%s",
            md_path.name,
            json_path.name,
            reconciliation["status_label"],
        )
        return md_path, json_path, audit_payload

    @staticmethod
    def _render_markdown_report(data: Dict[str, Any]) -> str:
        meta = data["report_metadata"]
        rec = data["reconciliation"]
        summary = data["daily_cdc_summary"]
        status_dist = data["silver_active_status_distribution"]
        region_dist = data["silver_active_region_distribution"]
        alerts = data["governance_alerts"]
        mutations = data["recent_mutations_sample"]

        badge = "CONFORME (ZERO DRIFT)" if rec["is_consistent"] else "ALERTA DE DIVERGÊNCIA"

        lines = [
            f"# Relatório Diário de Auditoria de Dados — Pipeline CDC (Camada Silver)",
            "",
            f"- **Data de Referência:** `{meta['report_date']}`",
            f"- **Gerado em (UTC):** `{meta['generated_at_utc']}`",
            f"- **Pipeline:** `{meta['pipeline']} v{meta['version']}`",
            f"- **Status de Reconciliação OLTP vs Silver:** **{badge}**",
            "",
            "---",
            "",
            "## 1. Reconciliação de Estado e Paridade Criptográfica (OLTP vs Silver)",
            "",
            "| Métrica de Qualidade / Paridade | Origem OLTP (`orders`) | Espelho Silver (`vw_silver_orders_active`) | Divergência (Drift) |",
            "| :--- | :---: | :---: | :---: |",
            f"| **Registros Ativos** | `{rec['oltp_active_rows']}` | `{rec['silver_active_rows']}` | `{rec['silver_active_rows'] - rec['oltp_active_rows']}` |",
            f"| **Registros Deletados (Tombstones Silver)** | `N/A (Hard Delete)` | `{rec['silver_tombstone_rows']}` | `Governado via _is_deleted=1` |",
            f"| **Volume Financeiro Ativo (GMV)** | `R$ {rec['oltp_total_gmv']:,.2f}` | `R$ {rec['silver_total_gmv']:,.2f}` | `R$ {rec['gmv_drift']:,.2f}` |",
            f"| **Hash SHA-256 do Conjunto Ativo** | `{rec['oltp_sha256'][:16]}...` | `{rec['silver_sha256'][:16]}...` | `{'MATCH EXATO' if rec['oltp_sha256'] == rec['silver_sha256'] else 'MISMATCH'}` |",
            "",
            "---",
            "",
            "## 2. Volumetria de Eventos CDC e Telemetria de Replicação",
            "",
            f"- **Lotes JSON Processados no Dia:** `{summary['batches_processed']}`",
            f"- **Faixa de LSN (Log Sequence Number):** `{summary['min_lsn']} -> {summary['max_lsn']}`",
            f"- **Total de Eventos Auditados:** `{summary['total_events']}`",
            f"  - `INSERT (c)`: **{summary['inserts']}** eventos (`+ R$ {summary['gross_inserted_value_brl']:,.2f}` adicionados)",
            f"  - `UPDATE (u)`: **{summary['updates']}** eventos (`R$ {summary['net_updated_value_brl']:+,.2f}` variação líquida)",
            f"  - `DELETE (d)`: **{summary['deletes']}** eventos (`- R$ {summary['gross_deleted_value_brl']:,.2f}` removidos)",
            f"  - `SKIPPED (Idempotência/Out-of-Order)`: **{summary['skipped_events']}** eventos barrados",
            f"- **Latência Média de Replicação (Source -> Silver):** `{summary['avg_replication_lag_ms']:.2f} ms` (Máx: `{summary['max_replication_lag_ms']} ms`)",
            "",
            "---",
            "",
            "## 3. Estado Atual da Camada Silver por Status Operacional",
            "",
            "| Status do Pedido | Quantidade Ativa | GMV Acumulado (R$) |",
            "| :--- | :---: | :---: |",
        ]

        if status_dist:
            for item in status_dist:
                lines.append(
                    f"| `{item['status']}` | {item['order_count']} | R$ {float(item['total_gmv']):,.2f} |"
                )
        else:
            lines.append("| _Sem registros ativos_ | 0 | R$ 0.00 |")

        lines.extend(
            [
                "",
                "## 4. Distribuição Geográfica na Camada Silver (Regiões)",
                "",
                "| Região | Pedidos Ativos | GMV Acumulado (R$) |",
                "| :--- | :---: | :---: |",
            ]
        )

        if region_dist:
            for item in region_dist:
                lines.append(
                    f"| `{item['region']}` | {item['order_count']} | R$ {float(item['total_gmv']):,.2f} |"
                )
        else:
            lines.append("| _Sem registros ativos_ | 0 | R$ 0.00 |")

        lines.extend(
            [
                "",
                "---",
                "",
                "## 5. Governança e Alertas de Auditoria (Deleções de Alto Valor >= R$ 3.000,00)",
                "",
            ]
        )

        if alerts["high_value_deletes"]:
            lines.extend(
                [
                    "| LSN | Transaction ID | Order ID | Valor Removido (R$) | Horário Aplicação (UTC) |",
                    "| :---: | :---: | :---: | :---: | :---: |",
                ]
            )
            for hvd in alerts["high_value_deletes"]:
                lines.append(
                    f"| `{hvd['lsn']}` | `{hvd['tx_id']}` | `{hvd['record_pk']}` | R$ {float(hvd['removed_value']):,.2f} | `{hvd['applied_at_utc']}` |"
                )
        else:
            lines.append("> Nenhuma exclusão física de alto valor (>= R$ 3.000,00) registrada no período.")

        lines.extend(
            [
                "",
                "---",
                "",
                "## 6. Amostra das Últimas 10 Mutações Aplicadas (Linhagem CDC)",
                "",
                "| LSN | Operação | Order ID | Impacto (R$) | Lag (ms) | Campos Alterados (Diff) |",
                "| :---: | :---: | :---: | :---: | :---: | :--- |",
            ]
        )

        for mut in mutations:
            diff_str = mut["changed_fields_json"] or "-"
            lines.append(
                f"| `{mut['lsn']}` | **{mut['op_type']}** | `{mut['record_pk']}` | R$ {float(mut['amount_delta']):+,.2f} | `{mut['replication_lag_ms']}` | `{diff_str}` |"
            )

        lines.append("")
        return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consumidor CDC da Camada Silver e Gerador de Relatório Diário de Auditoria."
    )
    parser.add_argument(
        "--report-date",
        type=str,
        default=None,
        help="Data de referência YYYY-MM-DD para o relatório diário (padrão: hoje UTC).",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Mantém os arquivos JSON no diretório de entrada após o processamento.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    consumer = SilverCDCConsumer(archive_processed=not args.no_archive)
    consumer.process_all_batches()
    consumer.generate_daily_audit_report(report_date=args.report_date)


if __name__ == "__main__":
    main()
