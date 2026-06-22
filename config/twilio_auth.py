"""Twilio webhook signature validation dependency.

Validates the X-Twilio-Signature header on inbound Twilio webhook requests.
Algorithm (per Twilio docs):
  1. Start with the full URL of the webhook endpoint.
  2. Sort POST form params alphabetically by key; concatenate key+value (no separators) to URL.
  3. Sign the resulting string with HMAC-SHA1 using TWILIO_AUTH_TOKEN as the key.
  4. Base64-encode the digest and compare to X-Twilio-Signature using constant-time comparison.

Returns HTTP 503 when TWILIO_AUTH_TOKEN is not configured.
Returns HTTP 403 when the signature is absent or does not match.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from fastapi import Header, HTTPException, Request


def compute_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    """Compute the expected Twilio HMAC-SHA1 signature for a given request.

    Pure function — no I/O. Safe to call in unit tests without a running server.
    """
    payload = url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
    mac = hmac.new(
        auth_token.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha1,
    )
    return base64.b64encode(mac.digest()).decode("utf-8")


async def validate_twilio_signature(
    request: Request,
    x_twilio_signature: str = Header(default=""),
) -> None:
    """FastAPI dependency for Twilio webhook routes.

    Usage:
        router = APIRouter()

        @router.post("/twilio/inbound", dependencies=[Depends(validate_twilio_signature)])
        async def inbound(...): ...
    """
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        raise HTTPException(status_code=503, detail="Twilio auth not configured.")

    url = str(request.url)
    form_data = await request.form()
    params = {k: str(v) for k, v in form_data.items()}

    expected = compute_signature(auth_token, url, params)

    if not hmac.compare_digest(expected, x_twilio_signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature.")
