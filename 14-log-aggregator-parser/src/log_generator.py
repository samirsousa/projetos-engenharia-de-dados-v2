"""
Gerador de Logs Simulados de Servidores Web / API Gateway (Stage 1).

Simula o arquivo de log centralizado (`centralized_cluster_access.log`) proveniente de um cluster
de 4 nós Nginx/Envoy combinando:
- Tráfego legítimo de clientes (HTTP 200, 201, 204, 301) em rotas REST dinâmicas com IDs e UUIDs.
- Erros de cliente (HTTP 400, 401, 403, 404, 429) incluindo scanners de vulnerabilidade (`.env`, `/wp-admin`, SQLi).
- Erros críticos de servidor (HTTP 500, 502, 503, 504) concentrados em janelas de degradação de banco de dados.
- Linhas corrompidas de socket (Malformed Lines) para validar a resiliência do parser Regex e a Dead-Letter Queue.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple

from src.config import CLUSTER_NODES, RAW_LOG_FILE_PATH, ensure_directories

LEGITIMATE_CLIENT_IPS = [
    "177.84.120.15",
    "189.40.22.108",
    "200.155.80.42",
    "179.110.45.201",
    "201.68.14.99",
    "191.252.60.12",
    "187.12.90.33",
    "170.238.11.74",
    "10.240.0.10",    # Internal K8s Kubelet / Prometheus Probe
    "192.168.10.50",  # Internal BFF Service
]

SUSPICIOUS_SCANNER_IPS = [
    "185.220.101.44",  # Tor Exit / Vulnerability Scanner
    "45.155.205.109",  # Brute-force Auth Bot
    "198.51.100.77",   # SQLi / Path Traversal Attacker
    "203.0.113.195",   # Aggressive Scraper (404 / 429)
]

USER_AGENTS_NORMAL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) Mobile/15E148 FinApp-iOS/4.8.2",
    "okhttp/4.12.0 FinApp-Android/4.8.1",
    "kube-probe/1.30",
]

USER_AGENTS_ATTACK = [
    "sqlmap/1.8.4#stable (https://sqlmap.org)",
    "Mozilla/5.0 (compatible; Nikto/2.5.0)",
    "python-requests/2.31.0 (CredentialStuffingBot)",
    "curl/8.6.0-scanner",
]


def _weighted_choice(rng: random.Random, items: List[Tuple[Any, float]]) -> Any:
    total = sum(w for _, w in items)
    r = rng.uniform(0.0, total)
    acc = 0.0
    for val, weight in items:
        if acc + weight >= r:
            return val
        acc += weight
    return items[-1][0]


class ServerLogSimulator:
    """Gerador determinístico de arquivos de log estendidos de servidores HTTP/API Gateway."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.sample_uuids = [
            str(uuid.UUID(int=self.rng.getrandbits(128), version=4))
            for _ in range(35)
        ]

    def generate_log_lines(self, total_lines: int = 3200) -> Dict[str, Any]:
        lines: List[str] = []
        base_dt = datetime(2026, 11, 2, 8, 0, 0)
        current_dt = base_dt

        corrupted_indices = {250, 610, 980, 1340, 1720, 2110, 2490, 2850, 3050, 3180}

        for idx in range(1, total_lines + 1):
            current_dt = current_dt + timedelta(milliseconds=self.rng.randint(150, 2400))

            if idx in corrupted_indices:
                lines.append(
                    f"[CORRUPTED_STREAM_FRAME #{idx}] <<<INVALID_TCP_PAYLOAD_TRUNCATED_AT_{current_dt.strftime('%H:%M:%S')}>>>"
                )
                continue

            node_id = self.rng.choice(CLUSTER_NODES)
            trace_id = f"TRC-{idx:06d}-{self.rng.randint(1000, 9999)}"
            ts_str = current_dt.strftime("%d/%b/%Y:%H:%M:%S -0300")

            # Janela de Incidente de Banco de Dados (linhas 1400 a 1680 têm pico de erro 500/502/503/504)
            in_incident_window = 1400 <= idx <= 1680

            traffic_type = _weighted_choice(
                self.rng,
                [
                    ("NORMAL_TRAFFIC", 0.72 if not in_incident_window else 0.45),
                    ("SERVER_5XX_ERROR", 0.06 if not in_incident_window else 0.42),
                    ("CLIENT_404_MISSING", 0.12 if not in_incident_window else 0.07),
                    ("SECURITY_ATTACK_PROBE", 0.10 if not in_incident_window else 0.06),
                ],
            )

            if traffic_type == "NORMAL_TRAFFIC":
                client_ip = self.rng.choice(LEGITIMATE_CLIENT_IPS)
                auth_user = f"usr_{self.rng.randint(101, 550)}" if client_ip != "10.240.0.10" else "system_probe"
                ua = "kube-probe/1.30" if client_ip == "10.240.0.10" else self.rng.choice(USER_AGENTS_NORMAL[:-1])
                referer = "https://app.enterprise-portal.com.br/dashboard"

                route_choice = self.rng.randint(1, 7)
                if route_choice == 1:
                    method = "GET"
                    uri = f"/api/v1/orders/{self.rng.randint(10000, 99999)}/details?currency=BRL"
                    status = 200
                    bytes_sent = self.rng.randint(1450, 8900)
                    rt_ms = round(self.rng.uniform(18.0, 95.0), 2)
                elif route_choice == 2:
                    method = "POST"
                    uri = f"/api/v1/orders/{self.rng.randint(10000, 99999)}/checkout"
                    status = 201
                    bytes_sent = self.rng.randint(620, 1800)
                    rt_ms = round(self.rng.uniform(45.0, 165.0), 2)
                elif route_choice == 3:
                    method = "GET"
                    u_id = self.rng.choice(self.sample_uuids)
                    uri = f"/api/v1/users/{u_id}/profile"
                    status = 200
                    bytes_sent = self.rng.randint(980, 3200)
                    rt_ms = round(self.rng.uniform(14.0, 72.0), 2)
                elif route_choice == 4:
                    method = "POST"
                    uri = "/api/v1/payments/authorize"
                    status = 200
                    bytes_sent = self.rng.randint(540, 1200)
                    rt_ms = round(self.rng.uniform(65.0, 210.0), 2)
                elif route_choice == 5:
                    method = "GET"
                    uri = f"/api/v1/catalog/products/{self.rng.randint(100, 999)}?page=1&limit=20"
                    status = 200
                    bytes_sent = self.rng.randint(4200, 24500)
                    rt_ms = round(self.rng.uniform(12.0, 68.0), 2)
                elif route_choice == 6:
                    method = "GET"
                    uri = "/healthz"
                    status = 200
                    bytes_sent = 64
                    rt_ms = round(self.rng.uniform(1.2, 6.5), 2)
                else:
                    method = "DELETE"
                    uri = f"/api/v1/sessions/{self.rng.randint(1000, 9999)}"
                    status = 204
                    bytes_sent = 0
                    rt_ms = round(self.rng.uniform(9.0, 32.0), 2)

                uct_ms = round(max(0.8, rt_ms * self.rng.uniform(0.68, 0.92)), 2)

            elif traffic_type == "CLIENT_404_MISSING":
                client_ip = self.rng.choice(LEGITIMATE_CLIENT_IPS[:8] + [SUSPICIOUS_SCANNER_IPS[3]])
                auth_user = "-"
                ua = self.rng.choice(USER_AGENTS_NORMAL)
                referer = "https://app.enterprise-portal.com.br/"
                method = "GET"
                uri = self.rng.choice(
                    [
                        f"/api/v1/orders/{self.rng.randint(900000, 999999)}/invoice.pdf",
                        "/api/v1/legacy/reports/export",
                        "/assets/icons/favicon-old.ico",
                        f"/api/v1/catalog/products/{self.rng.randint(80000, 89999)}",
                    ]
                )
                status = 404
                bytes_sent = self.rng.randint(190, 420)
                rt_ms = round(self.rng.uniform(8.0, 38.0), 2)
                uct_ms = round(rt_ms * 0.75, 2)

            elif traffic_type == "SERVER_5XX_ERROR":
                client_ip = self.rng.choice(LEGITIMATE_CLIENT_IPS[:8])
                auth_user = f"usr_{self.rng.randint(101, 550)}"
                ua = self.rng.choice(USER_AGENTS_NORMAL[:-1])
                referer = "https://app.enterprise-portal.com.br/checkout"
                status = _weighted_choice(
                    self.rng, [(500, 0.52), (502, 0.16), (503, 0.18), (504, 0.14)]
                )
                if status in (500, 504):
                    method = "POST"
                    uri = self.rng.choice(
                        [
                            "/api/v1/payments/authorize",
                            f"/api/v1/orders/{self.rng.randint(10000, 99999)}/checkout",
                            "/api/v1/ledger/reconcile",
                        ]
                    )
                else:
                    method = "GET"
                    uri = f"/api/v1/orders/{self.rng.randint(10000, 99999)}/details"

                bytes_sent = self.rng.randint(240, 680)
                rt_ms = (
                    round(self.rng.uniform(1850.0, 5020.0), 2)
                    if status == 504
                    else round(self.rng.uniform(490.0, 1750.0), 2)
                )
                uct_ms = round(rt_ms * 0.96, 2)

            else:
                # SECURITY_ATTACK_PROBE (SQLi, Path Traversal, Brute-Force Auth, Sensitive File Probe)
                client_ip = self.rng.choice(SUSPICIOUS_SCANNER_IPS)
                auth_user = "-"
                ua = self.rng.choice(USER_AGENTS_ATTACK)
                referer = "-"
                attack_kind = self.rng.randint(1, 4)

                if attack_kind == 1:
                    method = "GET"
                    uri = "/api/v1/catalog/products/105?filter=1%27%20OR%20%271%27=%271%20UNION%20SELECT%20password%20FROM%20users--"
                    status = self.rng.choice([403, 400, 500])
                elif attack_kind == 2:
                    method = "GET"
                    uri = "/static/../../../../etc/passwd"
                    status = self.rng.choice([403, 404])
                elif attack_kind == 3:
                    method = "GET"
                    uri = self.rng.choice(
                        [
                            "/.env",
                            "/wp-admin/setup-config.php",
                            "/phpmyadmin/index.php",
                            "/.git/config",
                        ]
                    )
                    status = 404
                else:
                    method = "POST"
                    uri = "/api/v1/auth/login"
                    status = self.rng.choice([401, 429])

                bytes_sent = self.rng.randint(160, 512)
                rt_ms = round(self.rng.uniform(5.0, 44.0), 2)
                uct_ms = round(rt_ms * 0.65, 2)

            log_line = (
                f'[{node_id}] {client_ip} - {auth_user} [{ts_str}] '
                f'"{method} {uri} HTTP/1.1" {status} {bytes_sent} '
                f'"{referer}" "{ua}" rt={rt_ms:.2f} uct={uct_ms:.2f} trace_id={trace_id}'
            )
            lines.append(log_line)

        return {
            "lines": lines,
            "total_lines": len(lines),
            "corrupted_count": len(corrupted_indices),
        }


def write_simulated_log_file(
    total_lines: int = 3200,
    seed: int = 42,
    output_path: Path = RAW_LOG_FILE_PATH,
) -> Dict[str, Any]:
    """Gera o arquivo `.log` no disco e retorna metadados de geração."""
    ensure_directories()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sim = ServerLogSimulator(seed=seed)
    result = sim.generate_log_lines(total_lines=total_lines)
    output_path.write_text("\n".join(result["lines"]) + "\n", encoding="utf-8")
    return {
        "log_file_path": str(output_path),
        "total_lines": result["total_lines"],
        "expected_corrupted_lines": result["corrupted_count"],
    }
