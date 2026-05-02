"""API key authentication dependency.

Reads the expected key from the API_KEY environment variable.
API_KEY must be set — the server refuses to start without it (see app/main.py lifespan).
If the request header does not match, HTTP 403 is returned.

Usage:
    from config.auth import require_api_key
    router = APIRouter(dependencies=[Depends(require_api_key)])
"""

import os

from fastapi import Header, HTTPException


def require_api_key(x_api_key: str = Header(default="")) -> None:
    expected = os.environ.get("API_KEY", "")
    if not expected:
        # API_KEY missing at request time means the startup guard was bypassed.
        # Refuse the request rather than silently allowing open access.
        raise HTTPException(status_code=503, detail="Server authentication is not configured.")
    if x_api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
