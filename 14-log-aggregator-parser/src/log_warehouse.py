"""
Módulo de Persistência Relacional SQLite, Agregação de Métricas (por IP, Rota, Status Code e Nó)
e Geração do Relatório Analítico de Saúde do Servidor SRE (Stage 3).
"""

from __future__ import annotations

import csv
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Any

from src.config import (
    HTTP_STATUS_CATALOG,
    PARSED_EXPORTS_DIR,
    REPORTS_DIR,
    SLO_AVAILABILITY_TARGET_PCT,
    SQLITE_DB_PATH,
    ensure_directories,
)


def _percentile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    w = pos - lo
    return sorted_vals[lo] * (1.0 - w) + sorted_vals[hi] * w


class LogRelationalWarehouse:
    """Carrega os logs parseados no SQLite e constrói tabelas agregadas por IP, Rota, Status Code e Nó."""

    def __init__(self, db_path: Path = SQLITE_DB_PATH) -> None:
        self.db_path = db_path

    def load_and_aggregate(
        self, parsed_bundle: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        ensure_directories()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        events = parsed_bundle["parsed_events"]
        quarantine = parsed_bundle["quarantined_lines"]

        agg_by_ip = self._build_agg_by_ip(events)
        agg_by_route = self._build_agg_by_route(events)
        agg_by_status = self._build_agg_by_status_code(events)
        agg_by_node = self._build_agg_by_node(events)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.executescript(
                """
                DROP TABLE IF EXISTS agg_metrics_by_node;
                DROP TABLE IF EXISTS agg_metrics_by_status_code;
                DROP TABLE IF EXISTS agg_metrics_by_route;
                DROP TABLE IF EXISTS agg_metrics_by_ip;
                DROP TABLE IF EXISTS quarantine_unparseable_logs;
                DROP TABLE IF EXISTS fact_access_logs;

                CREATE TABLE fact_access_logs (
                    log_id INTEGER PRIMARY KEY,
                    line_number INTEGER NOT NULL,
                    trace_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    client_ip TEXT NOT NULL,
                    ip_scope TEXT NOT NULL,
                    auth_user TEXT NOT NULL,
                    event_timestamp TEXT NOT NULL,
                    minute_bucket TEXT NOT NULL,
                    http_method TEXT NOT NULL,
                    raw_uri TEXT NOT NULL,
                    raw_path TEXT NOT NULL,
                    normalized_route TEXT NOT NULL,
                    query_string TEXT NOT NULL,
                    http_protocol TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    status_class TEXT NOT NULL,
                    is_error_4xx INTEGER NOT NULL,
                    is_error_5xx INTEGER NOT NULL,
                    response_bytes INTEGER NOT NULL,
                    referer TEXT NOT NULL,
                    user_agent TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    upstream_ms REAL NOT NULL,
                    apdex_zone TEXT NOT NULL,
                    security_threat_type TEXT NOT NULL
                );

                CREATE TABLE quarantine_unparseable_logs (
                    line_number INTEGER PRIMARY KEY,
                    raw_log_line TEXT NOT NULL,
                    failure_reason TEXT NOT NULL
                );

                CREATE TABLE agg_metrics_by_ip (
                    client_ip TEXT PRIMARY KEY,
                    ip_scope TEXT NOT NULL,
                    total_requests INTEGER NOT NULL,
                    status_2xx_count INTEGER NOT NULL,
                    status_404_count INTEGER NOT NULL,
                    status_4xx_count INTEGER NOT NULL,
                    status_500_count INTEGER NOT NULL,
                    status_5xx_count INTEGER NOT NULL,
                    error_rate_pct REAL NOT NULL,
                    total_response_kb REAL NOT NULL,
                    avg_latency_ms REAL NOT NULL,
                    p95_latency_ms REAL NOT NULL,
                    security_threat_hits INTEGER NOT NULL,
                    primary_threat_type TEXT NOT NULL,
                    ip_reputation_status TEXT NOT NULL
                );

                CREATE TABLE agg_metrics_by_route (
                    route_key TEXT PRIMARY KEY,
                    http_method TEXT NOT NULL,
                    normalized_route TEXT NOT NULL,
                    total_requests INTEGER NOT NULL,
                    status_200_count INTEGER NOT NULL,
                    status_404_count INTEGER NOT NULL,
                    status_4xx_count INTEGER NOT NULL,
                    status_500_count INTEGER NOT NULL,
                    status_5xx_count INTEGER NOT NULL,
                    error_4xx_pct REAL NOT NULL,
                    error_5xx_pct REAL NOT NULL,
                    avg_latency_ms REAL NOT NULL,
                    p95_latency_ms REAL NOT NULL,
                    p99_latency_ms REAL NOT NULL,
                    apdex_score REAL NOT NULL,
                    route_health_status TEXT NOT NULL
                );

                CREATE TABLE agg_metrics_by_status_code (
                    status_code INTEGER PRIMARY KEY,
                    status_class TEXT NOT NULL,
                    status_description TEXT NOT NULL,
                    total_occurrences INTEGER NOT NULL,
                    traffic_share_pct REAL NOT NULL,
                    avg_latency_ms REAL NOT NULL,
                    max_latency_ms REAL NOT NULL,
                    total_response_kb REAL NOT NULL,
                    distinct_ips_count INTEGER NOT NULL,
                    most_affected_route TEXT NOT NULL
                );

                CREATE TABLE agg_metrics_by_node (
                    node_id TEXT PRIMARY KEY,
                    total_requests INTEGER NOT NULL,
                    status_2xx_count INTEGER NOT NULL,
                    status_4xx_count INTEGER NOT NULL,
                    status_5xx_count INTEGER NOT NULL,
                    availability_slo_pct REAL NOT NULL,
                    avg_latency_ms REAL NOT NULL,
                    p95_latency_ms REAL NOT NULL,
                    apdex_score REAL NOT NULL,
                    node_health_status TEXT NOT NULL
                );

                CREATE INDEX idx_logs_ip ON fact_access_logs(client_ip, status_code);
                CREATE INDEX idx_logs_route ON fact_access_logs(normalized_route, status_code);
                CREATE INDEX idx_logs_status ON fact_access_logs(status_code, event_timestamp);
                """
            )

            tables = [
                ("fact_access_logs", events),
                ("quarantine_unparseable_logs", quarantine),
                ("agg_metrics_by_ip", agg_by_ip),
                ("agg_metrics_by_route", agg_by_route),
                ("agg_metrics_by_status_code", agg_by_status),
                ("agg_metrics_by_node", agg_by_node),
            ]
            counts: Dict[str, int] = {}
            for tbl_name, rows in tables:
                if not rows:
                    counts[tbl_name] = 0
                    continue
                cols = list(rows[0].keys())
                placeholders = ", ".join(["?"] * len(cols))
                sql = f"INSERT INTO {tbl_name} ({', '.join(cols)}) VALUES ({placeholders})"
                cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
                counts[tbl_name] = len(rows)

            conn.commit()

            global_kpis = self._compute_global_sre_kpis(events, quarantine)
            return {
                "table_counts": counts,
                "agg_by_ip": agg_by_ip,
                "agg_by_route": agg_by_route,
                "agg_by_status": agg_by_status,
                "agg_by_node": agg_by_node,
                "quarantine": quarantine,
                "global_kpis": global_kpis,
            }
        finally:
            conn.close()

    def _build_agg_by_ip(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for e in events:
            grouped[e["client_ip"]].append(e)

        rows: List[Dict[str, Any]] = []
        for ip, items in grouped.items():
            n = len(items)
            s_2xx = sum(1 for x in items if 200 <= x["status_code"] < 300)
            s_404 = sum(1 for x in items if x["status_code"] == 404)
            s_4xx = sum(x["is_error_4xx"] for x in items)
            s_500 = sum(1 for x in items if x["status_code"] == 500)
            s_5xx = sum(x["is_error_5xx"] for x in items)
            err_pct = round(((s_4xx + s_5xx) / n) * 100.0, 2)

            latencies = sorted(x["latency_ms"] for x in items)
            avg_lat = round(sum(latencies) / n, 2)
            p95_lat = round(_percentile(latencies, 0.95), 2)
            total_kb = round(sum(x["response_bytes"] for x in items) / 1024.0, 2)

            threats = [
                x["security_threat_type"]
                for x in items
                if x["security_threat_type"] != "NONE"
            ]
            threat_hits = len(threats)
            primary_threat = Counter(threats).most_common(1)[0][0] if threats else "NONE"

            if threat_hits >= 5 or err_pct >= 65.0:
                reputation = "MALICIOUS_BLOCK_WAF"
            elif threat_hits > 0 or err_pct >= 30.0:
                reputation = "SUSPICIOUS_RATE_LIMIT"
            else:
                reputation = "TRUSTED_CLIENT"

            rows.append(
                {
                    "client_ip": ip,
                    "ip_scope": items[0]["ip_scope"],
                    "total_requests": n,
                    "status_2xx_count": s_2xx,
                    "status_404_count": s_404,
                    "status_4xx_count": s_4xx,
                    "status_500_count": s_500,
                    "status_5xx_count": s_5xx,
                    "error_rate_pct": err_pct,
                    "total_response_kb": total_kb,
                    "avg_latency_ms": avg_lat,
                    "p95_latency_ms": p95_lat,
                    "security_threat_hits": threat_hits,
                    "primary_threat_type": primary_threat,
                    "ip_reputation_status": reputation,
                }
            )

        rows.sort(key=lambda r: (r["security_threat_hits"], r["total_requests"]), reverse=True)
        return rows

    def _build_agg_by_route(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for e in events:
            grouped[(e["http_method"], e["normalized_route"])].append(e)

        rows: List[Dict[str, Any]] = []
        for (method, route), items in grouped.items():
            n = len(items)
            s_200 = sum(1 for x in items if x["status_code"] == 200)
            s_404 = sum(1 for x in items if x["status_code"] == 404)
            s_4xx = sum(x["is_error_4xx"] for x in items)
            s_500 = sum(1 for x in items if x["status_code"] == 500)
            s_5xx = sum(x["is_error_5xx"] for x in items)

            err_4xx_pct = round((s_4xx / n) * 100.0, 2)
            err_5xx_pct = round((s_5xx / n) * 100.0, 2)

            latencies = sorted(x["latency_ms"] for x in items)
            avg_lat = round(sum(latencies) / n, 2)
            p95_lat = round(_percentile(latencies, 0.95), 2)
            p99_lat = round(_percentile(latencies, 0.99), 2)

            satisfied = sum(1 for x in items if x["apdex_zone"] == "SATISFIED")
            tolerating = sum(1 for x in items if x["apdex_zone"] == "TOLERATING")
            apdex = round((satisfied + 0.5 * tolerating) / n, 4)

            if err_5xx_pct >= 10.0 or apdex < 0.75:
                health = "CRITICAL_DEGRADATION"
            elif err_4xx_pct >= 50.0:
                health = "HIGH_CLIENT_ERROR_OR_SCAN"
            elif err_5xx_pct >= 2.0 or apdex < 0.90:
                health = "WARNING_LATENCY_SLO"
            else:
                health = "HEALTHY_OPTIMAL"

            rows.append(
                {
                    "route_key": f"{method} {route}",
                    "http_method": method,
                    "normalized_route": route,
                    "total_requests": n,
                    "status_200_count": s_200,
                    "status_404_count": s_404,
                    "status_4xx_count": s_4xx,
                    "status_500_count": s_500,
                    "status_5xx_count": s_5xx,
                    "error_4xx_pct": err_4xx_pct,
                    "error_5xx_pct": err_5xx_pct,
                    "avg_latency_ms": avg_lat,
                    "p95_latency_ms": p95_lat,
                    "p99_latency_ms": p99_lat,
                    "apdex_score": apdex,
                    "route_health_status": health,
                }
            )

        rows.sort(key=lambda r: (r["status_5xx_count"], r["total_requests"]), reverse=True)
        return rows

    def _build_agg_by_status_code(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        total_events = max(1, len(events))
        for e in events:
            grouped[e["status_code"]].append(e)

        rows: List[Dict[str, Any]] = []
        for code, items in sorted(grouped.items()):
            n = len(items)
            meta = HTTP_STATUS_CATALOG.get(
                code, {"class": f"{code // 100}xx", "description": "Other HTTP Status"}
            )
            latencies = [x["latency_ms"] for x in items]
            distinct_ips = len({x["client_ip"] for x in items})
            top_route = Counter(x["normalized_route"] for x in items).most_common(1)[0][0]

            rows.append(
                {
                    "status_code": code,
                    "status_class": meta["class"],
                    "status_description": meta["description"],
                    "total_occurrences": n,
                    "traffic_share_pct": round((n / total_events) * 100.0, 2),
                    "avg_latency_ms": round(sum(latencies) / n, 2),
                    "max_latency_ms": round(max(latencies), 2),
                    "total_response_kb": round(sum(x["response_bytes"] for x in items) / 1024.0, 2),
                    "distinct_ips_count": distinct_ips,
                    "most_affected_route": top_route,
                }
            )

        rows.sort(key=lambda r: r["total_occurrences"], reverse=True)
        return rows

    def _build_agg_by_node(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for e in events:
            grouped[e["node_id"]].append(e)

        rows: List[Dict[str, Any]] = []
        for node_id, items in sorted(grouped.items()):
            n = len(items)
            s_2xx = sum(1 for x in items if 200 <= x["status_code"] < 300)
            s_4xx = sum(x["is_error_4xx"] for x in items)
            s_5xx = sum(x["is_error_5xx"] for x in items)
            availability_pct = round(((n - s_5xx) / n) * 100.0, 2)

            latencies = sorted(x["latency_ms"] for x in items)
            avg_lat = round(sum(latencies) / n, 2)
            p95_lat = round(_percentile(latencies, 0.95), 2)

            satisfied = sum(1 for x in items if x["apdex_zone"] == "SATISFIED")
            tolerating = sum(1 for x in items if x["apdex_zone"] == "TOLERATING")
            apdex = round((satisfied + 0.5 * tolerating) / n, 4)

            health = (
                "HEALTHY_SLO_MET"
                if availability_pct >= SLO_AVAILABILITY_TARGET_PCT
                else "SLO_BREACH_INVESTIGATE"
            )

            rows.append(
                {
                    "node_id": node_id,
                    "total_requests": n,
                    "status_2xx_count": s_2xx,
                    "status_4xx_count": s_4xx,
                    "status_5xx_count": s_5xx,
                    "availability_slo_pct": availability_pct,
                    "avg_latency_ms": avg_lat,
                    "p95_latency_ms": p95_lat,
                    "apdex_score": apdex,
                    "node_health_status": health,
                }
            )

        return rows

    def _compute_global_sre_kpis(
        self,
        events: List[Dict[str, Any]],
        quarantine: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        n = max(1, len(events))
        s_200 = sum(1 for x in events if x["status_code"] == 200)
        s_2xx = sum(1 for x in events if 200 <= x["status_code"] < 300)
        s_404 = sum(1 for x in events if x["status_code"] == 404)
        s_4xx = sum(x["is_error_4xx"] for x in events)
        s_500 = sum(1 for x in events if x["status_code"] == 500)
        s_5xx = sum(x["is_error_5xx"] for x in events)

        latencies = sorted(x["latency_ms"] for x in events)
        satisfied = sum(1 for x in events if x["apdex_zone"] == "SATISFIED")
        tolerating = sum(1 for x in events if x["apdex_zone"] == "TOLERATING")
        apdex = round((satisfied + 0.5 * tolerating) / n, 4)

        availability_pct = round(((n - s_5xx) / n) * 100.0, 2)
        threat_events = sum(1 for x in events if x["security_threat_type"] != "NONE")

        return {
            "total_raw_lines": len(events) + len(quarantine),
            "parsed_valid_events": len(events),
            "quarantined_malformed_lines": len(quarantine),
            "parse_success_rate_pct": round(
                (len(events) / max(1, len(events) + len(quarantine))) * 100.0, 2
            ),
            "status_200_count": s_200,
            "status_2xx_count": s_2xx,
            "status_404_count": s_404,
            "status_4xx_count": s_4xx,
            "status_500_count": s_500,
            "status_5xx_count": s_5xx,
            "availability_slo_pct": availability_pct,
            "error_5xx_rate_pct": round((s_5xx / n) * 100.0, 2),
            "error_4xx_rate_pct": round((s_4xx / n) * 100.0, 2),
            "avg_latency_ms": round(sum(latencies) / n, 2),
            "p95_latency_ms": round(_percentile(latencies, 0.95), 2),
            "p99_latency_ms": round(_percentile(latencies, 0.99), 2),
            "global_apdex_score": apdex,
            "security_threat_events": threat_events,
            "total_bandwidth_mb": round(
                sum(x["response_bytes"] for x in events) / (1024.0 * 1024.0), 2
            ),
        }


def export_aggregated_csvs_and_sre_report(
    warehouse_results: Dict[str, Any],
    exports_dir: Path = PARSED_EXPORTS_DIR,
    report_path: Path = REPORTS_DIR / "server_health_sre_report.md",
) -> Dict[str, str]:
    """Exporta as tabelas agregadas em CSV e gera o Relatório Analítico de Saúde do Servidor SRE."""
    ensure_directories()
    exports_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    exported: Dict[str, str] = {}
    for name in ("agg_by_ip", "agg_by_route", "agg_by_status", "agg_by_node", "quarantine"):
        rows = warehouse_results[name]
        if not rows:
            continue
        csv_path = exports_dir / f"{name}.csv"
        fieldnames = list(rows[0].keys())
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        exported[name] = str(csv_path)

    k = warehouse_results["global_kpis"]
    lines = [
        "# Relatório Analítico SRE: Saúde do Servidor, Agregação de Logs & Segurança",
        "",
        "## 1. Sumário Executivo dos Quatro Sinais de Ouro (SRE Golden Signals)",
        "",
        "| Métrica SRE / Observabilidade | Valor Consolidado | Meta / Diagnóstico |",
        "| :--- | ---: | :--- |",
        f"| **Total de Linhas de Log Processadas** | `{k['total_raw_lines']:,}` | Stream centralizado do cluster |",
        f"| **Eventos Estruturados via Regex** | `{k['parsed_valid_events']:,}` | Taxa de sucesso de `{k['parse_success_rate_pct']:.2f}%` |",
        f"| **Linhas Malformadas em Quarentena (DLQ)** | `{k['quarantined_malformed_lines']}` | Isoladas sem interrupção do parser |",
        f"| **Disponibilidade Global (Non-5xx SLO)** | **`{k['availability_slo_pct']:.2f}%`** | Meta SLO `>= {SLO_AVAILABILITY_TARGET_PCT:.2f}%` |",
        f"| **Requisições com Sucesso (`2xx` / `HTTP 200`)** | `{k['status_2xx_count']:,}` (`{k['status_200_count']:,}` HTTP 200) | Tráfego saudável atendido |",
        f"| **Erros de Cliente (`4xx` / `HTTP 404`)** | `{k['status_4xx_count']:,}` (`{k['status_404_count']:,}` HTTP 404) | Taxa 4xx: `{k['error_4xx_rate_pct']:.2f}%` |",
        f"| **Erros Críticos de Servidor (`5xx` / `HTTP 500`)** | `{k['status_5xx_count']:,}` (`{k['status_500_count']:,}` HTTP 500) | Taxa 5xx: `{k['error_5xx_rate_pct']:.2f}%` |",
        f"| **Latência Média / P95 / P99** | `{k['avg_latency_ms']:.2f} ms` / `{k['p95_latency_ms']:.2f} ms` / `{k['p99_latency_ms']:.2f} ms` | Perfil de tempo de resposta |",
        f"| **Índice Global Apdex ($T = 120\\text{{ ms}}$)** | **`{k['global_apdex_score']:.4f}`** | Satisfação de tempo de resposta |",
        f"| **Tentativas de Ataque Detectadas via Regex** | `{k['security_threat_events']}` | SQLi, Path Traversal, Brute-Force & Scans |",
        f"| **Volume de Tráfego Egresso** | `{k['total_bandwidth_mb']:.2f} MB` | Banda total consumida |",
        "",
        "---",
        "",
        "## 2. Agregação por Código de Status HTTP (`agg_metrics_by_status_code`)",
        "",
        "| Status Code | Classe HTTP | Descrição Técnica | Ocorrências | % Tráfego | Latência Média (ms) | Latência Máx (ms) | IPs Distintos | Rota Mais Afetada |",
        "| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |",
    ]

    for s in warehouse_results["agg_by_status"]:
        lines.append(
            f"| **`{s['status_code']}`** | `{s['status_class']}` | {s['status_description']} | "
            f"**{s['total_occurrences']:,}** | `{s['traffic_share_pct']:.2f}%` | "
            f"{s['avg_latency_ms']:.2f} | {s['max_latency_ms']:.2f} | "
            f"{s['distinct_ips_count']} | `{s['most_affected_route']}` |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Agregação por Rota Normalizada (`agg_metrics_by_route`)",
            "",
            "| Verbo | Rota Canônica Normalizada (Regex) | Hits | HTTP 200 | HTTP 404 | HTTP 500 | Taxa 4xx % | Taxa 5xx % | Latência Média (ms) | P95 (ms) | Apdex | Status de Saúde |",
            "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
        ]
    )

    for r in warehouse_results["agg_by_route"]:
        lines.append(
            f"| `{r['http_method']}` | `{r['normalized_route']}` | {r['total_requests']:,} | "
            f"{r['status_200_count']:,} | {r['status_404_count']:,} | {r['status_500_count']:,} | "
            f"`{r['error_4xx_pct']:.1f}%` | **`{r['error_5xx_pct']:.1f}%`** | "
            f"{r['avg_latency_ms']:.1f} | {r['p95_latency_ms']:.1f} | "
            f"`{r['apdex_score']:.3f}` | `{r['route_health_status']}` |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Agregação por Endereço IP Cliente & Reputação WAF (`agg_metrics_by_ip`)",
            "",
            "| Endereço IP | Escopo | Requisições | 2xx | HTTP 404 | HTTP 500 | Taxa de Erro % | Banda (KB) | Latência Média (ms) | Hits de Ataque | Vetor de Ameaça Predominante | Reputação / Ação WAF |",
            "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | :--- |",
        ]
    )

    for ip_row in warehouse_results["agg_by_ip"]:
        lines.append(
            f"| `{ip_row['client_ip']}` | `{ip_row['ip_scope']}` | {ip_row['total_requests']:,} | "
            f"{ip_row['status_2xx_count']:,} | {ip_row['status_404_count']:,} | {ip_row['status_500_count']:,} | "
            f"`{ip_row['error_rate_pct']:.1f}%` | {ip_row['total_response_kb']:,.1f} | "
            f"{ip_row['avg_latency_ms']:.1f} | **`{ip_row['security_threat_hits']}`** | "
            f"`{ip_row['primary_threat_type']}` | **`{ip_row['ip_reputation_status']}`** |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 5. Saúde Operacional por Nó do Cluster (`agg_metrics_by_node`)",
            "",
            "| Node ID | Total Hits | Sucesso 2xx | Erros 4xx | Erros 5xx | Disponibilidade SLO % | Latência Média (ms) | P95 (ms) | Apdex | Status do Nó |",
            "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
        ]
    )

    for n_row in warehouse_results["agg_by_node"]:
        lines.append(
            f"| `{n_row['node_id']}` | {n_row['total_requests']:,} | {n_row['status_2xx_count']:,} | "
            f"{n_row['status_4xx_count']:,} | {n_row['status_5xx_count']:,} | "
            f"**`{n_row['availability_slo_pct']:.2f}%`** | {n_row['avg_latency_ms']:.2f} | "
            f"{n_row['p95_latency_ms']:.2f} | `{n_row['apdex_score']:.4f}` | `{n_row['node_health_status']}` |"
        )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    exported["sre_markdown_report"] = str(report_path)
    return exported
