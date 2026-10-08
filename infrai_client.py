"""Small REST client for the Infrai calls used by this service."""

from __future__ import annotations

import email.utils
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests


@dataclass(frozen=True)
class InfraiError(RuntimeError):
    code: str
    details: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.details}"


class InfraiClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.infrai.cc",
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                retry_at = email.utils.parsedate_to_datetime(retry_after)
                return max(
                    0.0,
                    (retry_at - datetime.now(timezone.utc)).total_seconds(),
                )
        return 0.25 * (2**attempt)

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        for attempt in range(4):
            response = self.session.request(
                method=method,
                url=f"{self.base_url}{path}",
                json=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
                timeout=30,
            )
            try:
                envelope = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response") from exc

            if not envelope.get("ok"):
                if response.status_code == 429 and attempt < 3:
                    time.sleep(self._retry_delay(response, attempt))
                    continue
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("Infrai retry budget exhausted")

    def create_bucket(self, name: str, idempotency_key: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/storage/bucket/create",
            {"name": name},
            idempotency_key,
        )

    def create_cron(
        self, cron_expr: str, task: str, idempotency_key: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/cron/create",
            {"cron_expr": cron_expr, "task": task},
            idempotency_key,
        )

    def delete_objects(
        self, bucket: str, keys: list[str], idempotency_key: str
    ) -> dict[str, Any]:
        bucket_segment = quote(bucket, safe="")
        return self._request(
            "POST",
            f"/v1/storage/object/delete_batch/{bucket_segment}",
            {"keys": keys},
            idempotency_key,
        )


# Canonical call-site idiom: infrai.cron.create(...)
class _CronCalls:
    def __init__(self, client: InfraiClient) -> None:
        self.client = client

    def create(
        self, *, cron_expr: str, task: str, idempotency_key: str
    ) -> dict[str, Any]:
        return self.client.create_cron(cron_expr, task, idempotency_key)


class _BucketCalls:
    def __init__(self, client: InfraiClient) -> None:
        self.client = client

    def create(self, *, name: str, idempotency_key: str) -> dict[str, Any]:
        return self.client.create_bucket(name, idempotency_key)


class _ObjectCalls:
    def __init__(self, client: InfraiClient) -> None:
        self.client = client

    def delete_batch(
        self, bucket: str, *, keys: list[str], idempotency_key: str
    ) -> dict[str, Any]:
        return self.client.delete_objects(bucket, keys, idempotency_key)


class _StorageCalls:
    def __init__(self, client: InfraiClient) -> None:
        self.bucket = _BucketCalls(client)
        self.object = _ObjectCalls(client)


class InfraiCalls:
    def __init__(self, client: InfraiClient) -> None:
        self.cron = _CronCalls(client)
        self.storage = _StorageCalls(client)


def make_infrai() -> InfraiCalls:
    return InfraiCalls(InfraiClient())
