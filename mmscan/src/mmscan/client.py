"""seats.aero Partner API client: auth, pacing, retries and a DB-backed call counter."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from mmscan.store import Store

BASE_URL = "https://seats.aero/partnerapi/"
AUTH_HEADER = "Partner-Authorization"
KEY_ENV = "SEATS_AERO_API_KEY"
MIN_INTERVAL_S = 0.5  # at most two requests per second
MAX_RETRIES = 3

log = logging.getLogger("mmscan.client")


class ApiError(Exception):
    pass


class AuthError(ApiError):
    pass


class CapReached(ApiError):
    pass


class NotFound(ApiError):
    pass


class QuotaExhausted(ApiError):
    pass


def redact(headers: dict[str, str] | httpx.Headers) -> dict[str, str]:
    return {
        k: ("REDACTED" if k.lower() == AUTH_HEADER.lower() else v) for k, v in dict(headers).items()
    }


def _remaining(resp: httpx.Response) -> int | None:
    value = resp.headers.get("X-RateLimit-Remaining")
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _result_count(data: Any) -> int | None:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return len(data["data"])
    return None


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class Client:
    def __init__(
        self,
        api_key: str,
        store: Store,
        run_id: int | None,
        daily_cap: int,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
    ):
        if not api_key:
            raise ApiError(f"{KEY_ENV} is empty")
        self._key = api_key
        self.store = store
        self.run_id = run_id
        self.daily_cap = daily_cap
        self._sleep = sleep
        self._clock = clock
        self._last_start: float | None = None
        self._http = httpx.Client(
            base_url=base_url,
            headers={AUTH_HEADER: api_key, "Accept": "application/json"},
            transport=transport,
            timeout=timeout,
        )
        self.calls_made = 0

    @classmethod
    def from_env(
        cls,
        store: Store,
        run_id: int | None,
        daily_cap: int,
        dotenv_path: Path | None = None,
        **kwargs: Any,
    ) -> Client:
        load_dotenv(dotenv_path or Path(".env"))
        key = os.environ.get(KEY_ENV, "").strip()
        if not key:
            raise ApiError(
                f"{KEY_ENV} is not set. Put it in .env (see .env.example) or the environment."
            )
        return cls(key, store, run_id, daily_cap, **kwargs)

    @property
    def api_key(self) -> str:
        """Only for scrubbing the key out of saved responses. Never log it."""
        return self._key

    def close(self) -> None:
        self._http.close()

    def _pace(self) -> None:
        if self._last_start is not None:
            wait = MIN_INTERVAL_S - (self._clock() - self._last_start)
            if wait > 0:
                self._sleep(wait)
        self._last_start = self._clock()

    def _check_cap(self) -> None:
        used = self.store.calls_today()
        if used >= self.daily_cap:
            raise CapReached(
                f"Stopped: {used} calls made today, which reaches api.daily_call_cap "
                f"({self.daily_cap}). Raise the cap in config.yaml or wait until midnight UTC."
            )

    def get(self, path: str, params: dict[str, Any]) -> tuple[Any, httpx.Response]:
        params = {k: v for k, v in params.items() if v is not None}
        params = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in params.items()}
        endpoint = "/" + path.lstrip("/")
        last_error = "no attempt made"
        for attempt in range(MAX_RETRIES + 1):
            self._check_cap()
            self._pace()
            wall = time.perf_counter()
            try:
                resp = self._http.get(path.lstrip("/"), params=params)
            except httpx.TransportError as e:
                ms = int((time.perf_counter() - wall) * 1000)
                self.store.record_call(self.run_id, endpoint, params, None, ms, None, None)
                self.calls_made += 1
                log.info(
                    "GET %s params=%s status=error (%s) %dms",
                    endpoint,
                    params,
                    type(e).__name__,
                    ms,
                )
                last_error = f"{type(e).__name__}: {e}"
                if attempt < MAX_RETRIES:
                    self._sleep(2.0**attempt)
                    continue
                raise ApiError(f"GET {endpoint} failed after retries: {last_error}") from e
            ms = int((time.perf_counter() - wall) * 1000)
            remaining = _remaining(resp)
            data: Any = None
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError as e:
                    self.store.record_call(self.run_id, endpoint, params, 200, ms, None, remaining)
                    self.calls_made += 1
                    raise ApiError(f"GET {endpoint} returned invalid JSON") from e
            count = _result_count(data)
            self.store.record_call(
                self.run_id, endpoint, params, resp.status_code, ms, count, remaining
            )
            self.calls_made += 1
            log.info(
                "GET %s params=%s status=%d %dms results=%s remaining=%s",
                endpoint,
                params,
                resp.status_code,
                ms,
                count,
                remaining,
            )
            log.debug("request headers: %s", redact(resp.request.headers))

            status = resp.status_code
            if status == 200:
                return data, resp
            if status in (401, 403):
                raise AuthError(
                    f"GET {endpoint} returned {status}. The API key is missing, invalid or "
                    f"regenerated, or the request is malformed. API access may not be enabled "
                    f"for this seats.aero account."
                )
            if status == 404:
                raise NotFound(f"GET {endpoint} returned 404")
            if status == 429 or status >= 500:
                if remaining == 0:
                    raise QuotaExhausted(
                        f"GET {endpoint} returned {status} with no calls left today "
                        f"(X-RateLimit-Remaining: 0). The allowance resets at midnight UTC."
                    )
                last_error = f"status {status}"
                if attempt < MAX_RETRIES:
                    wait = _retry_after(resp)
                    self._sleep(wait if wait is not None else 2.0**attempt)
                    continue
                break
            raise ApiError(f"GET {endpoint} returned {status}: {resp.text[:300]}")
        raise ApiError(f"GET {endpoint} failed after {MAX_RETRIES} retries: {last_error}")
