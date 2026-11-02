"""
Utilitários de Segurança e Autenticação Criptográfica de Webhooks (HMAC-SHA256).
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from src.database import WebhookAuthError


def compute_hmac_sha256(secret_key: str, raw_body: bytes) -> str:
    """Calcula a assinatura HMAC-SHA256 no formato `sha256=<hex_digest>`."""
    digest = hmac.new(secret_key.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_webhook_signature(
    secret_key: str,
    raw_body: bytes,
    signature_header: Optional[str],
    require_signature: bool = False,
) -> bool:
    """
    Valida a assinatura HMAC-SHA256 usando comparação em tempo constante (`hmac.compare_digest`)
    contra ataques de temporização (Timing Attacks).
    """
    if not signature_header:
        if require_signature:
            raise WebhookAuthError(
                "Cabeçalho 'X-Webhook-Signature' ausente. Este endpoint exige assinatura HMAC-SHA256."
            )
        return True

    expected = compute_hmac_sha256(secret_key, raw_body)
    if not hmac.compare_digest(expected, signature_header.strip()):
        raise WebhookAuthError(
            "Assinatura criptográfica 'X-Webhook-Signature' inválida para o payload recebido."
        )
    return True
