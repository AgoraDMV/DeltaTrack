"""Shared HTTP helpers."""

from __future__ import annotations

import sys
import time

import httpx

BASE_URL = "https://api.congress.gov/v3"
LOG_API_REQUESTS = True

def request_with_retry(
    client: httpx.Client,
    url: str,
    params: dict | None = None,
    *,
    headers: dict | None = None,
    timeout: float | None = None,
    attempts: int = 3,
) -> httpx.Response:
    """GET with retry on 429 and 5xx."""
    if LOG_API_REQUESTS:
        safe_params = {k: v for k, v in (params or {}).items() if k != "api_key"}
        suffix = f" {safe_params}" if safe_params else ""
        print(f"[API]: {url}{suffix}", file=sys.stderr)

    request_kwargs: dict = {}
    if params is not None:
        request_kwargs["params"] = params
    if headers is not None:
        request_kwargs["headers"] = headers
    if timeout is not None:
        request_kwargs["timeout"] = timeout

    last_resp = None
    for attempt in range(attempts):
        last_resp = client.get(url, **request_kwargs)
        if last_resp.status_code == 429:
            print("Rate limited, waiting 60s...", file=sys.stderr)
            time.sleep(60)
            continue
        if last_resp.status_code >= 500:
            time.sleep(2**attempt)
            continue
        last_resp.raise_for_status()
        return last_resp

    last_resp.raise_for_status()
    return last_resp

def api_get(
    client: httpx.Client,
    path: str,
    *,
    api_key: str,
    params: dict | None = None,
) -> dict:
    """GET a congress.gov API v3 JSON endpoint with retries.

    Ensures we always use a fully-qualified URL (avoids relative-URL regressions).
    """
    url = f"{BASE_URL}{path}"
    request_params = dict(params or {})
    request_params["api_key"] = api_key
    resp = request_with_retry(client, url, request_params)
    return resp.json()