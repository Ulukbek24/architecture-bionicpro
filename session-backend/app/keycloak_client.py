from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException

from .settings import settings


class KeycloakClient:
    def __init__(self) -> None:
        self.realm_internal = f"{settings.keycloak_internal_url}/realms/{settings.keycloak_realm}"
        self.realm_public = f"{settings.keycloak_public_url}/realms/{settings.keycloak_realm}"
        self._jwks: dict | None = None

    def authorize_url(self, state: str, code_challenge: str, kc_idp_hint: str | None = None) -> str:
        params = {
            "client_id": settings.keycloak_client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": f"{settings.bff_public_url}/auth/callback",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if kc_idp_hint:
            params["kc_idp_hint"] = kc_idp_hint
        return f"{self.realm_public}/protocol/openid-connect/auth?{urlencode(params)}"

    async def exchange_code(self, code: str, code_verifier: str) -> dict:
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.keycloak_client_id,
            "client_secret": settings.keycloak_client_secret,
            "code": code,
            "redirect_uri": f"{settings.bff_public_url}/auth/callback",
            "code_verifier": code_verifier,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.realm_internal}/protocol/openid-connect/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail=f"token exchange failed: {resp.text}")
        return resp.json()

    async def refresh(self, refresh_token: str) -> dict:
        data = {
            "grant_type": "refresh_token",
            "client_id": settings.keycloak_client_id,
            "client_secret": settings.keycloak_client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.realm_internal}/protocol/openid-connect/token",
                data=data,
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="refresh failed")
        return resp.json()

    async def logout(self, refresh_token: str) -> None:
        data = {
            "client_id": settings.keycloak_client_id,
            "client_secret": settings.keycloak_client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{self.realm_internal}/protocol/openid-connect/logout", data=data)

    async def jwks(self) -> dict:
        if self._jwks:
            return self._jwks
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.realm_internal}/protocol/openid-connect/certs")
        resp.raise_for_status()
        self._jwks = resp.json()
        return self._jwks

    async def decode_access_token(self, access_token: str) -> dict:
        jwks = await self.jwks()
        unverified_header = jwt.get_unverified_header(access_token)
        kid = unverified_header.get("kid")
        key = None
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == kid:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
                break
        if key is None:
            raise HTTPException(status_code=401, detail="signing key not found")
        return jwt.decode(
            access_token,
            key=key,
            algorithms=[unverified_header.get("alg", "RS256")],
            options={"verify_aud": False},
        )


keycloak = KeycloakClient()
