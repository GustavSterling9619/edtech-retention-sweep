"""HTTP entry point for the edtech retention sweep."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException

from edtech_sweep import SweepDecision, SweepRequest, decide_sweep
from infrai_client import InfraiError, make_infrai


BUCKET = os.environ.get("EDTECH_ARCHIVE_BUCKET", "edtech-retention-archive")
app = FastAPI(title="Edtech retention sweep")


def _stable_key(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest}"


def schedule() -> dict[str, Any]:
    public_url = os.environ.get("PUBLIC_URL")
    if not public_url:
        raise RuntimeError("PUBLIC_URL must be set before registering the schedule")

    task = f"{public_url.rstrip('/')}/sweeps/edtech"
    infrai = make_infrai()
    bucket = infrai.storage.bucket.create(
        name=BUCKET,
        idempotency_key=_stable_key("edtech-bucket", BUCKET),
    )
    cron = infrai.cron.create(
        cron_expr="15 2 * * *",
        task=task,
        idempotency_key=_stable_key("edtech-cron", task),
    )
    return {"bucket": bucket, "cron": cron}


@app.post("/sweeps/edtech", response_model=SweepDecision)
def run_sweep(request: SweepRequest) -> SweepDecision:
    decision = decide_sweep(request)
    if not decision.delete_keys:
        return decision

    request_identity = request.model_dump_json()
    try:
        infrai = make_infrai()
        infrai.storage.object.delete_batch(
            BUCKET,
            keys=decision.delete_keys,
            idempotency_key=_stable_key("edtech-delete", request_identity),
        )
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=status,
            detail={"code": exc.code, "details": exc.details},
        ) from exc
    return decision


if __name__ == "__main__":
    if sys.argv[1:] == ["schedule"]:
        print(json.dumps(schedule(), sort_keys=True))
    elif sys.argv[1:]:
        raise SystemExit(f"unknown command: {' '.join(sys.argv[1:])}")
    else:
        uvicorn.run(app, host="0.0.0.0", port=8000)
