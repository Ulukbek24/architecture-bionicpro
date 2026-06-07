import secrets
import time
from typing import Optional

from .settings import settings

_store: dict[str, dict] = {}


def create_session(data: dict) -> str:
    sid = secrets.token_urlsafe(48)
    _store[sid] = {**data, "created_at": time.time()}
    return sid


def get_session(sid: Optional[str]) -> Optional[dict]:
    if not sid:
        return None
    return _store.get(sid)


def update_session(sid: str, data: dict) -> None:
    if sid in _store:
        _store[sid].update(data)


def delete_session(sid: Optional[str]) -> None:
    if sid and sid in _store:
        del _store[sid]


def new_pkce_pair() -> tuple[str, str]:
    import base64
    import hashlib

    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def new_state() -> str:
    return secrets.token_urlsafe(32)
