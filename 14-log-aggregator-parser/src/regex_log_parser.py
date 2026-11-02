"""
Motor de Extração, Normalização de Rotas e Classificação de Ameaças via Expressões Regulares Avançadas (Stage 2).

Implementa 5 expressões regulares compiladas (`re.VERBOSE` e Named Capture Groups `(?P<name>...)`):
1. `EXTENDED_ACCESS_LOG_REGEX`: Extrai cabeçalho de nó, IPv4 estrito, usuário, timestamp Apache/Nginx,
   verbo HTTP, URI bruta, protocolo, status code, bytes, referer, user-agent, `rt` (latência total),
   `uct` (latência upstream) e `trace_id`.
2. `URI_SPLIT_REGEX`: Separa `raw_path` e `query_string` sem usar `split` ingênuo.
3. `UUID_SEGMENT_REGEX` e `NUMERIC_ID_SEGMENT_REGEX`: Normalizam parâmetros dinâmicos de rota
   (ex: `/api/v1/orders/48291/checkout` -> `/api/v1/orders/{id}/checkout` e
   `/api/v1/users/550e8400.../profile` -> `/api/v1/users/{uuid}/profile`), evitando explosão de cardinalidade.
4. `SECURITY_THREAT_REGEXES`: Identifica ataques de SQL Injection, Path Traversal, Sensitive File Probing
   (`.env`, `/wp-admin`, `/phpmyadmin`) e Scanners Automatizados no User-Agent.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple

from src.config import (
    APDEX_SATISFIED_MS,
    APDEX_TOLERATING_MS,
    HTTP_STATUS_CATALOG,
    RAW_LOG_FILE_PATH,
)

# 1. Regex Principal de Extração do Log Estendido Nginx / Envoy (com Named Capture Groups e modo VERBOSE)
EXTENDED_ACCESS_LOG_REGEX = re.compile(
    r"""
    ^\[(?P<node_id>[a-zA-Z0-9._-]+)\]\s+                                  # Identificador do nó do cluster
    (?P<client_ip>(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}                # Validação estrita dos 3 primeiros octetos IPv4
                  (?:25[0-5]|2[0-4]\d|[01]?\d\d?))\s+                     # 4º octeto IPv4 (0..255)
    (?P<ident>\S+)\s+                                                     # RFC 1413 identity
    (?P<auth_user>\S+)\s+                                                 # Usuário autenticado ou '-'
    \[(?P<raw_timestamp>\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+[+-]\d{4})\]\s+  # Timestamp [dd/Mon/yyyy:HH:MM:SS tz]
    "(?P<http_method>GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+           # Verbo HTTP
     (?P<raw_uri>\S+)\s+                                                  # URI completa (path + query string)
     (?P<http_protocol>HTTP/\d\.\d)"\s+                                   # Protocolo HTTP/1.1 ou HTTP/2.0
    (?P<status_code>[1-5]\d{2})\s+                                        # Código de status HTTP (100..599)
    (?P<response_bytes>\d+)\s+                                            # Bytes transferidos no corpo
    "(?P<referer>[^"]*)"\s+                                               # Cabeçalho Referer
    "(?P<user_agent>[^"]*)"\s+                                            # Cabeçalho User-Agent
    rt=(?P<latency_ms>\d+(?:\.\d+)?)\s+                                   # Request Time total (ms)
    uct=(?P<upstream_ms>\d+(?:\.\d+)?)\s+                                 # Upstream Connect/Response Time (ms)
    trace_id=(?P<trace_id>[A-Za-z0-9_-]+)\s*$                             # Correlation Trace ID distribuído
    """,
    re.VERBOSE,
)

# 2. Decomposição de URI em Path e Query String
URI_SPLIT_REGEX = re.compile(r"^(?P<path>[^?#]+)(?:\?(?P<query>.*))?$")

# 3. Expressões Regulares de Normalização de Cardinalidade de Rotas REST
UUID_SEGMENT_REGEX = re.compile(
    r"(?<=/)[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?=/|$)"
)
NUMERIC_ID_PDF_REGEX = re.compile(r"(?<=/)\d+(?=\.pdf$)", re.IGNORECASE)
NUMERIC_ID_SEGMENT_REGEX = re.compile(r"(?<=/)\d+(?=/|$)")

# 4. Expressões Regulares de Detecção de Ameaças de Segurança (WAF / SIEM)
SQL_INJECTION_REGEX = re.compile(
    r"(?:union\s+select|or\s+(?:%27|')\d+(?:%27|')=(?:%27|')\d+|--|;\s*drop\s+table|%27\s*or\s*)",
    re.IGNORECASE,
)
PATH_TRAVERSAL_REGEX = re.compile(
    r"(?:(?:\.\./|\.\.\\|%2e%2e%2f)+|/etc/passwd|/windows/win\.ini)",
    re.IGNORECASE,
)
SENSITIVE_PROBE_REGEX = re.compile(
    r"^/(?:\.env|\.git(?:/.*)?|wp-admin(?:/.*)?|phpmyadmin(?:/.*)?|actuator(?:/.*)?)$",
    re.IGNORECASE,
)
SCANNER_UA_REGEX = re.compile(
    r"(?:sqlmap|nikto|nmap|credentialstuffingbot|curl/[\d.]+-scanner|masscan)",
    re.IGNORECASE,
)
PRIVATE_IPV4_REGEX = re.compile(
    r"^(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.|127\.)"
)


def normalize_route_path(raw_path: str) -> str:
    """
    Normaliza caminhos de URL dinâmicos para templates canônicos de rota:
    - `/api/v1/orders/48219/checkout` -> `/api/v1/orders/{id}/checkout`
    - `/api/v1/users/550e8400-e29b-41d4-a716-446655440000/profile` -> `/api/v1/users/{uuid}/profile`
    - `/static/../../../../etc/passwd` -> `/static/[PATH_TRAVERSAL_PROBE]`
    """
    if PATH_TRAVERSAL_REGEX.search(raw_path):
        return "/[SECURITY_PATH_TRAVERSAL_PROBE]"

    normalized = UUID_SEGMENT_REGEX.sub("{uuid}", raw_path)
    normalized = NUMERIC_ID_PDF_REGEX.sub("{id}", normalized)
    normalized = NUMERIC_ID_SEGMENT_REGEX.sub("{id}", normalized)
    return normalized


def classify_security_threat(raw_uri: str, raw_path: str, user_agent: str, status_code: int) -> str:
    """Classifica assinaturas de ataque cibernético usando Regex sobre URI e User-Agent."""
    if SQL_INJECTION_REGEX.search(raw_uri):
        return "SQL_INJECTION_ATTEMPT"
    if PATH_TRAVERSAL_REGEX.search(raw_uri):
        return "PATH_TRAVERSAL_ATTEMPT"
    if SENSITIVE_PROBE_REGEX.search(raw_path):
        return "SENSITIVE_FILE_SCAN"
    if raw_path == "/api/v1/auth/login" and status_code in (401, 429):
        return "BRUTE_FORCE_AUTH"
    if SCANNER_UA_REGEX.search(user_agent):
        return "AUTOMATED_VULN_SCANNER"
    return "NONE"


class RegexCentralizedLogParser:
    """Parser centralizado de alta precisão baseado em Regex compiladas com fila Dead-Letter."""

    def parse_file(self, log_file_path: Path = RAW_LOG_FILE_PATH) -> Dict[str, List[Dict[str, Any]]]:
        raw_lines = log_file_path.read_text(encoding="utf-8").splitlines()
        return self.parse_lines(raw_lines)

    def parse_lines(self, raw_lines: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        parsed_events: List[Dict[str, Any]] = []
        quarantined_lines: List[Dict[str, Any]] = []

        for line_num, raw_line in enumerate(raw_lines, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue

            match = EXTENDED_ACCESS_LOG_REGEX.match(stripped)
            if not match:
                quarantined_lines.append(
                    {
                        "line_number": line_num,
                        "raw_log_line": stripped[:500],
                        "failure_reason": "REGEX_PATTERN_MISMATCH_MALFORMED_STREAM",
                    }
                )
                continue

            groups = match.groupdict()
            status_code = int(groups["status_code"])
            response_bytes = int(groups["response_bytes"])
            latency_ms = float(groups["latency_ms"])
            upstream_ms = float(groups["upstream_ms"])

            # Parse do timestamp [02/Nov/2026:08:00:01 -0300] para ISO-8601 e bucket de minuto
            dt_obj = datetime.strptime(groups["raw_timestamp"], "%d/%b/%Y:%H:%M:%S %z")
            iso_timestamp = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            minute_bucket = dt_obj.strftime("%Y-%m-%d %H:%M:00")

            # Separação de Path e Query String via Regex
            uri_match = URI_SPLIT_REGEX.match(groups["raw_uri"])
            raw_path = uri_match.group("path") if uri_match else groups["raw_uri"]
            query_string = (uri_match.group("query") or "") if uri_match else ""

            normalized_route = normalize_route_path(raw_path)

            status_meta = HTTP_STATUS_CATALOG.get(
                status_code,
                {
                    "class": f"{status_code // 100}xx Unknown",
                    "description": "Unclassified HTTP Status",
                },
            )
            status_class = status_meta["class"]

            is_error_4xx = 1 if 400 <= status_code < 500 else 0
            is_error_5xx = 1 if 500 <= status_code < 600 else 0

            # Classificação Apdex (Satisfied / Tolerating / Frustrated)
            if is_error_5xx == 1 or latency_ms > APDEX_TOLERATING_MS:
                apdex_zone = "FRUSTRATED"
            elif latency_ms <= APDEX_SATISFIED_MS:
                apdex_zone = "SATISFIED"
            else:
                apdex_zone = "TOLERATING"

            ip_scope = (
                "INTERNAL_RFC1918"
                if PRIVATE_IPV4_REGEX.match(groups["client_ip"])
                else "EXTERNAL_PUBLIC"
            )
            threat_type = classify_security_threat(
                groups["raw_uri"], raw_path, groups["user_agent"], status_code
            )

            parsed_events.append(
                {
                    "log_id": len(parsed_events) + 1,
                    "line_number": line_num,
                    "trace_id": groups["trace_id"],
                    "node_id": groups["node_id"],
                    "client_ip": groups["client_ip"],
                    "ip_scope": ip_scope,
                    "auth_user": groups["auth_user"],
                    "event_timestamp": iso_timestamp,
                    "minute_bucket": minute_bucket,
                    "http_method": groups["http_method"],
                    "raw_uri": groups["raw_uri"],
                    "raw_path": raw_path,
                    "normalized_route": normalized_route,
                    "query_string": query_string,
                    "http_protocol": groups["http_protocol"],
                    "status_code": status_code,
                    "status_class": status_class,
                    "is_error_4xx": is_error_4xx,
                    "is_error_5xx": is_error_5xx,
                    "response_bytes": response_bytes,
                    "referer": groups["referer"],
                    "user_agent": groups["user_agent"],
                    "latency_ms": latency_ms,
                    "upstream_ms": upstream_ms,
                    "apdex_zone": apdex_zone,
                    "security_threat_type": threat_type,
                }
            )

        return {
            "parsed_events": parsed_events,
            "quarantined_lines": quarantined_lines,
        }
