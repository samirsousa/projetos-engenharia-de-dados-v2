"""
Orquestrador End-to-End do Pipeline de Change Data Capture (CDC).

Executa ondas sucessivas de simulação transacional (OLTP -> Conector CDC Bronze ->
Consumidor Silver -> Reconciliação Criptográfica SHA-256 -> Relatório Diário de Auditoria).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from src.cdc_connector import DebeziumCDCConnector
from src.config import PipelineConfig, setup_logger
from src.silver_consumer import SilverCDCConsumer
from src.transaction_generator import TransactionGenerator

logger = setup_logger("CDC-Orchestrator")


def run_end_to_end_simulation(
    clean_start: bool = False,
    waves: int = 3,
    events_per_wave: int = 20,
    batch_size: int = 10,
    seed: int = 42,
) -> None:
    config = PipelineConfig()

    if clean_start and config.data_dir.exists():
        logger.info("Limpando diretório de dados anterior (%s) para execução limpa...", config.data_dir)
        shutil.rmtree(config.data_dir)

    config.ensure_directories()

    generator = TransactionGenerator(config=config, seed=seed)
    connector = DebeziumCDCConnector(config=config, batch_size=batch_size)
    consumer = SilverCDCConsumer(config=config, archive_processed=True)

    logger.info("=" * 80)
    logger.info("INICIANDO PIPELINE DE CHANGE DATA CAPTURE (CDC) END-TO-END")
    logger.info("=" * 80)

    for wave_idx in range(1, waves + 1):
        logger.info("-" * 80)
        logger.info(
            "ONDA #%d/%d | 1. Gerando %d transações DML (INSERT/UPDATE/DELETE) no SQLite OLTP...",
            wave_idx,
            waves,
            events_per_wave,
        )
        generator.run_workload(num_events=events_per_wave, delay_seconds=0.01)

        logger.info("ONDA #%d/%d | 2. Executando Conector CDC (Debezium Simulator)...", wave_idx, waves)
        emitted_batches = connector.drain_all_pending()
        logger.info("ONDA #%d/%d | Arquivos JSON gerados na Bronze: %d", wave_idx, waves, len(emitted_batches))

        logger.info("ONDA #%d/%d | 3. Executando Consumidor Batch da Camada Silver...", wave_idx, waves)
        consumer.process_all_batches()

    logger.info("-" * 80)
    logger.info("4. Consolidando Reconciliação OLTP vs Silver e Relatório Diário de Auditoria...")
    md_report, json_report, audit_data = consumer.generate_daily_audit_report()
    rec = audit_data["reconciliation"]

    logger.info("=" * 80)
    logger.info("RESUMO EXECUTIVO DA EXECUÇÃO DO PIPELINE CDC")
    logger.info("  Status de Paridade : %s", rec["status_label"])
    logger.info("  Registros Ativos   : OLTP=%d | Silver=%d | Tombstones=%d", rec["oltp_active_rows"], rec["silver_active_rows"], rec["silver_tombstone_rows"])
    logger.info("  GMV Ativo Total    : OLTP=R$ %.2f | Silver=R$ %.2f (Drift=R$ %.2f)", rec["oltp_total_gmv"], rec["silver_total_gmv"], rec["gmv_drift"])
    logger.info("  SHA-256 Checksum   : %s", rec["oltp_sha256"])
    logger.info("  Relatório Markdown : %s", md_report)
    logger.info("  Relatório JSON     : %s", json_report)
    logger.info("=" * 80)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Orquestrador End-to-End do Pipeline CDC.")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove o diretório data/ antes de iniciar para uma simulação do zero.",
    )
    parser.add_argument(
        "--waves",
        type=int,
        default=3,
        help="Quantidade de ondas de simulação (padrão: 3).",
    )
    parser.add_argument(
        "--events-per-wave",
        type=int,
        default=20,
        help="Transações OLTP geradas por onda (padrão: 20).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Tamanho máximo do lote de eventos por arquivo JSON (padrão: 10).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed para reprodutibilidade determinística (padrão: 42).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_end_to_end_simulation(
        clean_start=args.clean,
        waves=args.waves,
        events_per_wave=args.events_per_wave,
        batch_size=args.batch_size,
        seed=args.seed,
    )
