import time
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from .keycloak_client import keycloak
from .sessions import (
    create_session,
    delete_session,
    get_session,
    new_pkce_pair,
    new_state,
    update_session,
)
from .settings import settings

app = FastAPI(title="BionicPRO BFF / Session Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _set_session_cookie(response: Response, sid: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=sid,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
        max_age=60 * 60 * 8,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")


async def _current_session(request: Request) -> dict:
    sid = request.cookies.get(settings.session_cookie_name)
    sess = get_session(sid)
    if not sess:
        raise HTTPException(status_code=401, detail="not authenticated")
    if sess.get("access_expires_at", 0) < time.time() + 10:
        tokens = await keycloak.refresh(sess["refresh_token"])
        update_session(
            sid,
            {
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token", sess["refresh_token"]),
                "access_expires_at": time.time() + tokens.get("expires_in", 300),
            },
        )
    return sess


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/auth/login")
async def auth_login(idp: str | None = None) -> RedirectResponse:
    verifier, challenge = new_pkce_pair()
    state = new_state()
    sid = create_session(
        {
            "pkce_verifier": verifier,
            "oauth_state": state,
            "stage": "pending",
        }
    )
    url = keycloak.authorize_url(state=state, code_challenge=challenge, kc_idp_hint=idp)
    response = RedirectResponse(url=url)
    _set_session_cookie(response, sid)
    return response


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str, state: str) -> RedirectResponse:
    sid = request.cookies.get(settings.session_cookie_name)
    sess = get_session(sid)
    if not sess or sess.get("oauth_state") != state:
        raise HTTPException(status_code=400, detail="invalid state")

    tokens = await keycloak.exchange_code(code, sess["pkce_verifier"])
    claims = await keycloak.decode_access_token(tokens["access_token"])

    update_session(
        sid,
        {
            "stage": "authenticated",
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "access_expires_at": time.time() + tokens.get("expires_in", 300),
            "user": {
                "sub": claims.get("sub"),
                "username": claims.get("preferred_username"),
                "email": claims.get("email"),
                "name": claims.get("name"),
                "roles": claims.get("realm_access", {}).get("roles", []),
                "prosthetic_ids": claims.get("prosthetic_ids", []),
            },
        },
    )
    response = RedirectResponse(url=settings.frontend_url)
    _set_session_cookie(response, sid)
    return response


@app.post("/auth/logout")
async def auth_logout(request: Request) -> Response:
    sid = request.cookies.get(settings.session_cookie_name)
    sess = get_session(sid)
    if sess and sess.get("refresh_token"):
        await keycloak.logout(sess["refresh_token"])
    delete_session(sid)
    response = JSONResponse({"status": "ok"})
    _clear_session_cookie(response)
    return response


@app.get("/me")
async def me(sess: dict = Depends(_current_session)) -> dict:
    return sess.get("user", {})


@app.get("/reports")
async def reports(sess: dict = Depends(_current_session)) -> JSONResponse:
    user = sess.get("user", {})
    if "prothetic_user" not in user.get("roles", []) and "administrator" not in user.get("roles", []):
        raise HTTPException(status_code=403, detail="role not permitted")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{settings.reports_api_url}/reports",
            params={
                "user_id": user.get("sub"),
                "prosthetic_ids": ",".join(user.get("prosthetic_ids", [])),
            },
            headers={"Authorization": f"Bearer {sess['access_token']}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return JSONResponse(resp.json())
