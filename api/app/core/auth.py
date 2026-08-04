import time

import httpx
from fastapi import Header, HTTPException
from jose import jwk, jwt
from jose.utils import base64url_decode

from app.core.config import settings

_JWKS_CACHE: dict = {"keys": [], "fetched_at": 0.0}
_JWKS_TTL_SECONDS = 3600


def _get_jwks() -> list[dict]:
    now = time.time()
    if not _JWKS_CACHE["keys"] or now - _JWKS_CACHE["fetched_at"] > _JWKS_TTL_SECONDS:
        response = httpx.get(settings.supabase_jwks_url, timeout=10.0)
        response.raise_for_status()
        _JWKS_CACHE["keys"] = response.json()["keys"]
        _JWKS_CACHE["fetched_at"] = now
    return _JWKS_CACHE["keys"]


def _find_key(kid: str, keys: list[dict]) -> dict | None:
    return next((k for k in keys if k.get("kid") == kid), None)


def verify_jwt(token: str) -> str:
    """Verify a Supabase-issued JWT's signature against its JWKS and return the user_id (sub)."""
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Malformed token") from exc

    kid = unverified_header.get("kid")
    keys = _get_jwks()
    key_data = _find_key(kid, keys) if kid else None
    if key_data is None:
        # Key rotated since our cache was populated — force one refresh before giving up.
        _JWKS_CACHE["fetched_at"] = 0.0
        keys = _get_jwks()
        key_data = _find_key(kid, keys) if kid else None
    if key_data is None:
        raise HTTPException(status_code=401, detail="Unknown signing key")

    public_key = jwk.construct(key_data)
    message, encoded_sig = token.rsplit(".", 1)
    signature = base64url_decode(encoded_sig.encode())
    if not public_key.verify(message.encode(), signature):
        raise HTTPException(status_code=401, detail="Invalid token signature")

    try:
        claims = jwt.get_unverified_claims(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Malformed token claims") from exc

    if claims.get("exp") is not None and time.time() > claims["exp"]:
        raise HTTPException(status_code=401, detail="Token expired")
    if settings.jwt_audience and claims.get("aud") != settings.jwt_audience:
        raise HTTPException(status_code=401, detail="Invalid token audience")

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing sub claim")
    return sub


def get_current_user_id(authorization: str = Header(default="")) -> str:
    if settings.disable_auth:
        if not settings.local_dev_user_id:
            raise HTTPException(status_code=500, detail="LOCAL_DEV_USER_ID is required when auth is disabled")
        return settings.local_dev_user_id
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    return verify_jwt(token)
