from fastapi import Depends, FastAPI, HTTPException, Query

from .auth import current_user
from .clickhouse import fetch_user_report
from .s3 import ensure_bucket, upload_report

app = FastAPI(title="BionicPRO reports-api")


@app.on_event("startup")
async def _startup() -> None:
    try:
        ensure_bucket()
    except Exception:
        # MinIO may not be ready yet; do not block API startup.
        pass


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/reports")
async def reports(
    prosthetic_ids: str = Query("", description="comma-separated prosthetic ids"),
    user: dict = Depends(current_user),
) -> dict:
    if "prothetic_user" not in user["roles"] and "administrator" not in user["roles"]:
        raise HTTPException(status_code=403, detail="role not permitted")

    allowed = set(user.get("prosthetic_ids", []))
    requested = {pid for pid in prosthetic_ids.split(",") if pid}

    if "administrator" in user["roles"]:
        effective = list(requested) if requested else list(allowed)
    else:
        effective = list(requested & allowed) if requested else list(allowed)

    if not effective:
        raise HTTPException(status_code=403, detail="no accessible prosthetic ids")

    data = fetch_user_report(effective)
    artifact = upload_report(user["sub"], data)
    return {**data, "artifact": artifact}
