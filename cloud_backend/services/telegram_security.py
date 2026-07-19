"""Small dependency-free Telegram webhook security helpers."""

from __future__ import annotations

import hmac


def verify_webhook_secret(configured_secret: str, received_header: str) -> bool:
    secret = str(configured_secret or "").strip()
    header = str(received_header or "")
    if not secret or not header:
        return False
    return hmac.compare_digest(secret, header)
