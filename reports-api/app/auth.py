import httpx
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .settings import settings

bearer = HTTPBearer(auto_error=True)

_jwks_cache: dict | None = None


async def _jwks() -> dict:
    global _jwks_cache
    if _jwks_cache:
        return _jwks_cache
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.keycloak_internal_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
        )
    resp.raise_for_status()
    _jwks_cache = resp.json()
    return _jwks_cache


async def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    token = credentials.credentials
    try:
        header = jwt.get_unverified_header(token)
        keys = (await _jwks()).get("keys", [])
        key_jwk = next((k for k in keys if k.get("kid") == header.get("kid")), None)
        if key_jwk is None:
            raise HTTPException(status_code=401, detail="signing key not found")
        key = jwt.algorithms.RSAAlgorithm.from_jwk(key_jwk)
        claims = jwt.decode(
            token,
            key=key,
            algorithms=[header.get("alg", "RS256")],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc

    roles = claims.get("realm_access", {}).get("roles", [])
    return {
        "sub": claims.get("sub"),
        "username": claims.get("preferred_username"),
        "roles": roles,
        "prosthetic_ids": claims.get("prosthetic_ids", []),
    }
