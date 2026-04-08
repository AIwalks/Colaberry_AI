"""API key authentication dependency.

Reads the expected key from the API_KEY environment variable.
If API_KEY is not set, the check is skipped (dev/local convenience).
If API_KEY is set and the request header does not match, HTTP 403 is returned.

Usage:
    from config.auth import require_api_key
    router = APIRouter(dependencies=[Depends(require_api_key)])
"""

import os

from fastapi import Header, HTTPException


def require_api_key(x_api_key: str = Header(default="")) -> None:
    expected = os.environ.get("API_KEY", "")
    if not expected:
        return  # API_KEY not configured — auth check bypassed
    if x_api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
