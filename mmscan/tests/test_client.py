import logging

import httpx
import pytest

from mmscan.client import ApiError, AuthError, CapReached, Client, NotFound, QuotaExhausted
from mmscan.store import Store

KEY = "pro_SECRETKEY123"


class FakeTime:
    def __init__(self):
        self.now = 1000.0
        self.waits: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.waits.append(s)
        self.now += s


def make_client(tmp_path, handler, cap=300):
    store = Store(tmp_path / "db.sqlite")
    t = FakeTime()
    client = Client(
        KEY,
        store,
        run_id=None,
        daily_cap=cap,
        transport=httpx.MockTransport(handler),
        sleep=t.sleep,
        clock=t.clock,
    )
    return client, store, t


def ok(json=None, remaining="900", **headers):
    return httpx.Response(
        200,
        json=json or {"data": [], "hasMore": False},
        headers={"X-RateLimit-Remaining": remaining, **headers},
    )


def test_sends_auth_header(tmp_path):
    seen = {}

    def handler(req):
        seen["auth"] = req.headers.get("Partner-Authorization")
        seen["url"] = str(req.url)
        return ok()

    client, store, _ = make_client(tmp_path, handler)
    data, resp = client.get("availability", {"source": "lufthansa", "cabin": None})
    assert seen["auth"] == KEY
    assert seen["url"] == "https://seats.aero/partnerapi/availability?source=lufthansa"
    assert data == {"data": [], "hasMore": False}
    assert store.last_rate_remaining() == 900


def test_401_raises_auth_error_with_access_message(tmp_path):
    client, _, _ = make_client(tmp_path, lambda r: httpx.Response(401, json={}))
    with pytest.raises(AuthError, match="API access may not be enabled"):
        client.get("availability", {})


def test_429_retries_then_succeeds(tmp_path):
    responses = [
        httpx.Response(429, headers={"Retry-After": "2", "X-RateLimit-Remaining": "50"}),
        ok(),
    ]
    client, store, t = make_client(tmp_path, lambda r: responses.pop(0))
    client.get("availability", {})
    assert t.waits == [2.0]
    assert store.calls_today() == 2


def test_500_gives_up_after_three_retries(tmp_path):
    attempts = []

    def handler(req):
        attempts.append(1)
        return httpx.Response(503)

    client, _, t = make_client(tmp_path, handler)
    with pytest.raises(ApiError):
        client.get("availability", {})
    assert len(attempts) == 4
    assert t.waits == [1.0, 2.0, 4.0]


def test_timeout_is_retried(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow", request=req)
        return ok()

    client, _, _ = make_client(tmp_path, handler)
    client.get("availability", {})
    assert len(calls) == 2


def test_429_with_zero_remaining_not_retried(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, headers={"X-RateLimit-Remaining": "0"})

    client, _, _ = make_client(tmp_path, handler)
    with pytest.raises(QuotaExhausted):
        client.get("availability", {})
    assert len(calls) == 1


def test_404_raises_not_found(tmp_path):
    client, _, _ = make_client(tmp_path, lambda r: httpx.Response(404, json={}))
    with pytest.raises(NotFound):
        client.get("trips/abc", {})


def test_cap_reached_before_request(tmp_path):
    sent = []

    def handler(req):
        sent.append(1)
        return ok()

    client, store, _ = make_client(tmp_path, handler, cap=2)
    client.get("availability", {})
    client.get("availability", {})
    with pytest.raises(CapReached, match="daily_call_cap"):
        client.get("availability", {})
    assert len(sent) == 2


def test_pacing_waits_between_calls(tmp_path):
    client, _, t = make_client(tmp_path, lambda r: ok())
    client.get("availability", {})
    t.now += 0.2
    client.get("availability", {})
    assert t.waits == [pytest.approx(0.3)]


def test_key_never_logged(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    client, _, _ = make_client(tmp_path, lambda r: ok())
    client.get("availability", {"source": "lufthansa"})
    assert "availability" in caplog.text
    assert KEY not in caplog.text


def test_missing_key_is_clear(tmp_path, monkeypatch):
    monkeypatch.delenv("SEATS_AERO_API_KEY", raising=False)
    with pytest.raises(ApiError, match="SEATS_AERO_API_KEY"):
        Client.from_env(Store(tmp_path / "db.sqlite"), None, 300, dotenv_path=tmp_path / ".env")
