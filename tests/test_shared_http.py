"""Tests for tools/shared/http.py retry semantics (issue #61).

Hermetic: every response is served through respx, and ``shared.http.time.sleep`` is
replaced by a recorder, so no test waits on a real backoff (the 429 branch sleeps 60s).
Recording the sleep arguments rather than discarding them is deliberate: the wait
*durations* are the part of the retry policy a refactor can silently change while the
call still succeeds, so the durations are asserted, not just the retry count.

``tests/test_fetch_govinfo.py`` covers 5xx retry through ``enumerate_versions``, but
does so at that function's observable contract -- explicitly "regardless of whether the
raise originates in request_with_retry or the retained guard". These tests pin the
helper itself, and cover the branches no caller-level test reaches: 429, non-retryable
4xx, and request-kwarg plumbing.
"""

from __future__ import annotations

import httpx
import pytest
import respx

import shared.http
from shared.http import api_get, request_with_retry

URL = "https://example.test/v3/thing"


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Replace the retry sleep with a recorder; returns the recorded durations."""
    recorded: list[float] = []
    monkeypatch.setattr(shared.http.time, "sleep", recorded.append)
    return recorded


class TestRetryOn429:
    """429 is the rate-limit branch: fixed 60s wait, then retry."""

    @respx.mock
    def test_429_then_200_returns_the_200_and_waits_60s(self, sleeps):
        route = respx.get(URL).mock(side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})])
        with httpx.Client() as client:
            resp = request_with_retry(client, URL)

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert route.call_count == 2
        # The rate-limit wait is a flat 60s, not the 5xx exponential backoff.
        assert sleeps == [60]

    @respx.mock
    def test_persistent_429_raises_after_exhausting_attempts(self, sleeps):
        route = respx.get(URL).mock(return_value=httpx.Response(429))
        with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError) as exc:
            request_with_retry(client, URL, attempts=3)

        # Must be loud: a rate-limited caller that got no data must not receive a
        # response object it would read as an empty-but-successful result.
        assert exc.value.response.status_code == 429
        assert route.call_count == 3
        # Three waits for three attempts: the last one happens after the final
        # attempt, immediately before the raise, and buys nothing. Pinned as the
        # current policy rather than endorsed -- see #257.
        assert sleeps == [60, 60, 60]


class TestMixedRetryBranches:
    """429 and 5xx in one sequence.

    Each branch is exercised alone elsewhere, which hides how they interact: the
    backoff exponent is the *loop index*, not a count of 5xx responses, so a 429
    earlier in the sequence advances the exponent and the first 5xx then waits longer
    than it would have on its own. Real sequences mix the two (a rate limit followed
    by a struggling server), and nothing else in this file would notice a refactor
    that decoupled the counters. Pinned as current policy, questioned in #257.
    """

    @respx.mock
    def test_429_then_5xx_then_success(self, sleeps):
        route = respx.get(URL).mock(side_effect=[httpx.Response(429), httpx.Response(503), httpx.Response(200)])
        with httpx.Client() as client:
            resp = request_with_retry(client, URL)

        assert resp.status_code == 200
        assert route.call_count == 3
        # 2**1, not 2**0: the 429 consumed attempt 0, so the first 5xx backs off as
        # though it were the second failure.
        assert sleeps == [60, 2]

    @respx.mock
    def test_5xx_then_429_then_success(self, sleeps):
        route = respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(429), httpx.Response(200)])
        with httpx.Client() as client:
            resp = request_with_retry(client, URL)

        assert resp.status_code == 200
        assert route.call_count == 3
        assert sleeps == [1, 60]

    @respx.mock
    def test_mixed_failures_still_raise_once_attempts_run_out(self, sleeps):
        respx.get(URL).mock(side_effect=[httpx.Response(429), httpx.Response(503), httpx.Response(500)])
        with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError) as exc:
            request_with_retry(client, URL, attempts=3)

        # The status raised is the last one seen, not the first.
        assert exc.value.response.status_code == 500


class TestAttemptsBoundary:
    @respx.mock
    def test_attempts_of_one_makes_a_single_call_and_does_not_retry(self, sleeps):
        route = respx.get(URL).mock(return_value=httpx.Response(503))
        with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
            request_with_retry(client, URL, attempts=1)

        assert route.call_count == 1
        # Still sleeps once before giving up, for the same reason as above (#257).
        assert sleeps == [1]

    @respx.mock
    def test_attempts_of_zero_fails_without_making_a_request(self, sleeps):
        # Degenerate but reachable if an attempts value is ever config-driven. The
        # loop never runs, so last_resp is still None and the post-loop
        # raise_for_status() raises AttributeError rather than an HTTP error the
        # caller could catch. Pinned so the crash is a known contract, not a
        # surprise; #257 covers making it a real error.
        route = respx.get(URL).mock(return_value=httpx.Response(200))
        with httpx.Client() as client, pytest.raises(AttributeError):
            request_with_retry(client, URL, attempts=0)

        assert route.call_count == 0


class TestRetryOn5xx:
    """5xx is the transient-server branch: exponential backoff, then retry."""

    @respx.mock
    def test_503_then_200_returns_the_200(self, sleeps):
        route = respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})])
        with httpx.Client() as client:
            resp = request_with_retry(client, URL)

        assert resp.status_code == 200
        assert route.call_count == 2
        assert sleeps == [1]  # 2**0

    @respx.mock
    def test_backoff_grows_exponentially_across_attempts(self, sleeps):
        respx.get(URL).mock(return_value=httpx.Response(500))
        with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
            request_with_retry(client, URL, attempts=4)

        # 2**attempt for attempt 0..3. A linear or constant backoff would still pass a
        # count-only assertion, so the sequence itself is pinned.
        assert sleeps == [1, 2, 4, 8]

    @respx.mock
    def test_persistent_5xx_raises_rather_than_returning_the_error_response(self, sleeps):
        route = respx.get(URL).mock(return_value=httpx.Response(500))
        with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError) as exc:
            request_with_retry(client, URL, attempts=2)

        assert exc.value.response.status_code == 500
        assert route.call_count == 2

    @respx.mock
    def test_500_is_retried_at_the_boundary(self, sleeps):
        # The branch is `>= 500`; 500 itself must be inside it.
        route = respx.get(URL).mock(side_effect=[httpx.Response(500), httpx.Response(200)])
        with httpx.Client() as client:
            request_with_retry(client, URL)
        assert route.call_count == 2


class TestNonRetryable4xx:
    """A 4xx other than 429 is a client error: fail fast, do not burn attempts."""

    @respx.mock
    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    def test_4xx_raises_immediately_without_retrying(self, sleeps, status):
        route = respx.get(URL).mock(return_value=httpx.Response(status))
        with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError) as exc:
            request_with_retry(client, URL, attempts=3)

        assert exc.value.response.status_code == status
        # The point of the assertion is the 1: retrying a 404 three times (with
        # backoff) would still raise, so only the call count distinguishes
        # fail-fast from a slow retry loop that happens to end in the same error.
        assert route.call_count == 1
        assert sleeps == []

    @respx.mock
    def test_499_is_not_treated_as_retryable(self, sleeps):
        # Guards the lower edge of the `>= 500` branch.
        route = respx.get(URL).mock(return_value=httpx.Response(499))
        with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
            request_with_retry(client, URL, attempts=3)
        assert route.call_count == 1


class TestSuccessPath:
    @respx.mock
    def test_200_returns_without_sleeping_or_retrying(self, sleeps):
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={"v": 1}))
        with httpx.Client() as client:
            resp = request_with_retry(client, URL)

        assert resp.json() == {"v": 1}
        assert route.call_count == 1
        assert sleeps == []

    @respx.mock
    def test_unfollowed_3xx_raises_rather_than_returning_a_bodyless_response(self, sleeps):
        # httpx's raise_for_status() raises on any non-2xx, 3xx included, so a
        # redirect that reaches this helper unfollowed is an error rather than a
        # returned response. It matters because the caller would otherwise get a
        # 304 with no body and .json() it. Not retried: 3xx is neither 429 nor >=500.
        route = respx.get(URL).mock(return_value=httpx.Response(304))
        with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError) as exc:
            request_with_retry(client, URL, attempts=3)

        assert exc.value.response.status_code == 304
        assert route.call_count == 1
        assert sleeps == []


class TestRequestKwargPlumbing:
    """params/headers/timeout are forwarded only when supplied.

    They are passed through a conditionally-built kwargs dict, so an omitted argument
    must leave httpx's own default in place rather than being forwarded as None.
    """

    @respx.mock
    def test_params_and_headers_reach_the_request(self, sleeps):
        route = respx.get(URL).mock(return_value=httpx.Response(200))
        with httpx.Client() as client:
            request_with_retry(client, URL, {"format": "json"}, headers={"X-Token": "abc"})

        request = route.calls[0].request
        assert request.url.params["format"] == "json"
        assert request.headers["X-Token"] == "abc"

    @respx.mock
    def test_omitted_timeout_does_not_forward_none(self, sleeps):
        # Forwarding timeout=None explicitly would disable the client timeout
        # entirely (httpx reads None as "wait forever"), turning a stalled server
        # into a hung run. Omission must instead leave the client default intact.
        route = respx.get(URL).mock(return_value=httpx.Response(200))
        with httpx.Client(timeout=7.0) as client:
            request_with_retry(client, URL)

        assert route.calls[0].request.extensions["timeout"]["read"] == 7.0

    @respx.mock
    def test_explicit_timeout_overrides_the_client_default(self, sleeps):
        route = respx.get(URL).mock(return_value=httpx.Response(200))
        with httpx.Client(timeout=7.0) as client:
            request_with_retry(client, URL, timeout=1.5)

        assert route.calls[0].request.extensions["timeout"]["read"] == 1.5

    @respx.mock
    def test_params_are_resent_on_retry(self, sleeps):
        # The kwargs dict is built once outside the loop; a refactor that mutated or
        # consumed it would drop the params on the retry and silently query the
        # wrong resource.
        route = respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(200)])
        with httpx.Client() as client:
            request_with_retry(client, URL, {"format": "json"})

        assert [c.request.url.params["format"] for c in route.calls] == ["json", "json"]


class TestLogging:
    @respx.mock
    def test_api_key_is_not_written_to_the_log_line(self, sleeps, capsys, monkeypatch):
        monkeypatch.setattr(shared.http, "LOG_API_REQUESTS", True)
        respx.get(URL).mock(return_value=httpx.Response(200, json={}))
        with httpx.Client() as client:
            request_with_retry(client, URL, {"format": "json", "api_key": "SECRET123"})

        err = capsys.readouterr().err
        assert "SECRET123" not in err
        # The redaction must drop the key, not the whole log line.
        assert "format" in err


class TestApiGet:
    @respx.mock
    def test_builds_an_absolute_url_and_injects_the_api_key(self, sleeps):
        route = respx.get(f"{shared.http.BASE_URL}/bill/119/hr").mock(
            return_value=httpx.Response(200, json={"bills": []})
        )
        with httpx.Client() as client:
            data = api_get(client, "/bill/119/hr", api_key="K")

        assert data == {"bills": []}
        request = route.calls[0].request
        assert str(request.url).startswith(shared.http.BASE_URL)
        assert request.url.params["api_key"] == "K"

    @respx.mock
    def test_does_not_mutate_the_caller_params_dict(self, sleeps):
        # api_get injects api_key into the params it was handed; doing so in place
        # would leak the key into a dict the caller may reuse or log.
        respx.get(f"{shared.http.BASE_URL}/bill").mock(return_value=httpx.Response(200, json={}))
        params = {"format": "json"}
        with httpx.Client() as client:
            api_get(client, "/bill", api_key="K", params=params)

        assert params == {"format": "json"}
