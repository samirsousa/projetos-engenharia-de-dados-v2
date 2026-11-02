"""
Orquestrador End-to-End do Projeto 14: Log Aggregator & Centralized Log Parser.

Executa sequencialmente:
1. Geração do arquivo de log centralizado de servidores (`centralized_cluster_access.log`) com códigos
   HTTP (200, 201, 204, 400, 401, 403, 404, 429, 500, 502, 503, 504), IPs, timestamps, latências e ataques.
2. Parseamento via Expressões Regulares Avançadas (`re.VERBOSE` + Named Capture Groups + Normalização de Rotas).
3. Carga em banco SQLite (`centralized_logs.db`) agregando métricas por IP, por rota, por status code e por nó.
4. Exportação de CSVs e geração do Relatório Analítico SRE de Saúde do Servidor (`server_health_sre_report.md`).
"""

from __future__ import annotations

import argparse
import shutil
import time
from typing import Dict, Any

from src.config import (
    DATA_DIR,
    PARSED_EXPORTS_DIR,
    RAW_LOG_FILE_PATH,
    REPORTS_DIR,
    SQLITE_DB_PATH,
    ensure_directories,
)
from src.log_generator import write_simulated_log_file
from src.log_warehouse import (
    LogRelationalWarehouse,
    export_aggregated_csvs_and_sre_report,
)
from src.regex_log_parser import RegexCentralizedLogParser


def run_log_aggregator_pipeline(
    clean: bool = False,
    seed: int = 42,
    total_lines: int = 3200,
) -> Dict[str, Any]:
    start_ts = time.perf_counter()

    if clean:
        for d in (DATA_DIR, REPORTS_DIR):
            if d.exists():
                shutil.rmtree(d)

    ensure_directories()

    print("=" * 86)
    print("  PROJETO 14: LOG AGGREGATOR & CENTRALIZED REGEX LOG PARSER (SRE PIPELINE)")
    print("=" * 86)

    # 1. Geração do Arquivo de Log
    print("\n[1/4] Gerando arquivo de log centralizado de cluster HTTP/Nginx...")
    gen_meta = write_simulated_log_file(
        total_lines=total_lines, seed=seed, output_path=RAW_LOG_FILE_PATH
    )
    print(f"      - Arquivo de log bruto : {gen_meta['log_file_path']}")
    print(f"      - Total de linhas      : {gen_meta['total_lines']:,}")

    # 2. Extração e Normalização com Regex Avançadas
    print("\n[2/4] Extraindo campos e normalizando rotas via Expressões Regulares compiladas...")
    parser = RegexCentralizedLogParser()
    parsed_bundle = parser.parse_file(RAW_LOG_FILE_PATH)
    print(f"      - Eventos HTTP estruturados : {len(parsed_bundle['parsed_events']):,}")
    print(f"      - Linhas corrompidas (DLQ)  : {len(parsed_bundle['quarantined_lines'])}")

    # 3. Carga SQLite e Agregações (por IP, Rota, Status Code e Nó)
    print("\n[3/4] Carregando banco SQLite e agregando métricas por IP, Rota e Código de Erro...")
    warehouse = LogRelationalWarehouse(db_path=SQLITE_DB_PATH)
    wh_res = warehouse.load_and_aggregate(parsed_bundle)
    for tbl, cnt in wh_res["table_counts"].items():
        print(f"      - {tbl:<32}: {cnt:>5,} registros")

    # 4. Relatório Analítico SRE e CSVs
    print("\n[4/4] Gerando Relatório Analítico SRE de Saúde do Servidor e arquivos CSV...")
    exported = export_aggregated_csvs_and_sre_report(
        wh_res, exports_dir=PARSED_EXPORTS_DIR
    )

    elapsed = time.perf_counter() - start_ts
    k = wh_res["global_kpis"]

    print("\n" + "=" * 86)
    print("  RESUMO EXECUTIVO DE SAÚDE DO SERVIDOR & OBSERVABILIDADE SRE")
    print("=" * 86)
    print(f"  * Total de Linhas Processadas         : {k['total_raw_lines']:,} ({k['parse_success_rate_pct']:.2f}% válidas)")
    print(f"  * Sucesso 2xx (HTTP 200)              : {k['status_2xx_count']:,} ({k['status_200_count']:,} HTTP 200)")
    print(f"  * Erros de Cliente 4xx (HTTP 404)     : {k['status_4xx_count']:,} ({k['status_404_count']:,} HTTP 404 | {k['error_4xx_rate_pct']:.2f}%)")
    print(f"  * Erros de Servidor 5xx (HTTP 500)    : {k['status_5xx_count']:,} ({k['status_500_count']:,} HTTP 500 | {k['error_5xx_rate_pct']:.2f}%)")
    print("-" * 86)
    print(f"  * Disponibilidade Global (Non-5xx SLO): {k['availability_slo_pct']:.2f}%")
    print(f"  * Latência Média / P95 / P99          : {k['avg_latency_ms']:.2f} ms / {k['p95_latency_ms']:.2f} ms / {k['p99_latency_ms']:.2f} ms")
    print(f"  * Índice Global Apdex (T = 120ms)     : {k['global_apdex_score']:.4f}")
    print(f"  * Eventos de Ataque / Scan Detectados : {k['security_threat_events']}")
    print("-" * 86)
    print(f"  * Banco Relacional SQLite             : {SQLITE_DB_PATH}")
    print(f"  * Relatório Analítico SRE (Markdown)  : {exported['sre_markdown_report']}")
    print("=" * 86)
    print(f"Pipeline de Agregação e Parseamento concluído em {elapsed:.2f}s.\n")

    return {
        "gen_meta": gen_meta,
        "table_counts": wh_res["table_counts"],
        "global_kpis": k,
        "exported": exported,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa o pipeline de geração, parseamento Regex e agregação SQLite de logs."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove artefatos anteriores antes da execução.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed aleatória para reprodutibilidade determinística (padrão: 42).",
    )
    args = parser.parse_args()
    run_log_aggregator_pipeline(clean=args.clean, seed=args.seed)


if __name__ == "__main__":
    main()
