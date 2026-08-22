"""Encryption at rest for the Pro payload.

The ledger repo is PUBLIC on purpose — its commit timestamps are the trust
anchor — which means anything committed in plaintext is world-readable at
raw.githubusercontent.com. The Pro slate therefore ships as ciphertext:
AES-256-GCM, key held only in GitHub Actions and Vercel secrets. The
committed blob doubles as a timestamped commitment to the Pro payload
itself.

Wire format (base64 of): nonce(12) || ciphertext || tag(16)
Node's crypto.createDecipheriv("aes-256-gcm") reads the same bytes.

The key is 64 hex chars in PRO_PAYLOAD_KEY. Everything here fails closed:
no key or a bad blob raises, and callers degrade to teaser-only behavior.
"""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_LEN = 12


def load_key() -> bytes:
    """PRO_PAYLOAD_KEY from the environment or the repo-root .env."""
    raw = os.environ.get("PRO_PAYLOAD_KEY", "")
    if not raw:
        env = Path(__file__).resolve().parents[1] / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("PRO_PAYLOAD_KEY="):
                    raw = line.split("=", 1)[1].strip()
                    break
    if len(raw) != 64:
        raise RuntimeError("PRO_PAYLOAD_KEY missing or not 64 hex chars")
    return bytes.fromhex(raw)


def encrypt(plaintext: str, key: bytes | None = None) -> str:
    key = key or load_key()
    nonce = secrets.token_bytes(NONCE_LEN)
    blob = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + blob).decode("ascii")


def decrypt(b64: str, key: bytes | None = None) -> str:
    key = key or load_key()
    raw = base64.b64decode(b64)
    nonce, blob = raw[:NONCE_LEN], raw[NONCE_LEN:]
    return AESGCM(key).decrypt(nonce, blob, None).decode("utf-8")
