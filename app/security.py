from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(payload: dict, secret: str, exp_minutes: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = payload | {
        "exp": int((datetime.now(UTC) + timedelta(minutes=exp_minutes)).timestamp()),
        "iat": int(datetime.now(UTC).timestamp()),
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        secret.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def decode_token(token: str, secret: str) -> dict:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            f"{header_b64}.{payload_b64}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected_signature, _b64url_decode(signature_b64)):
            raise ValueError("invalid signature")
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(datetime.now(UTC).timestamp()):
            raise ValueError("token expired")
        return payload
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid token") from exc
