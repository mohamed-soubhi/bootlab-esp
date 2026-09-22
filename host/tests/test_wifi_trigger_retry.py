"""WifiBoard.trigger: retries a timeout with headroom instead of leaking a raw urllib exception (soak evidence 2026-09-22:
failures clustered at 5.2-5.6s against the old 5.0s budget)."""
from __future__ import annotations

import urllib.error
from unittest.mock import patch

from labflash.idf_wifi_ota import TRIGGER_RETRIES, WifiBoard


def _board(tmp_path):
    for name in ("ca.pem",):
        (tmp_path / name).write_bytes(b"")
    import ssl
    with patch.object(ssl, "create_default_context"):
        return WifiBoard("192.168.1.152", "tok", tmp_path / "ca.pem")


def test_trigger_succeeds_first_try(tmp_path):
    b = _board(tmp_path)
    resp = type("R", (), {"status": 202, "__enter__": lambda s: s, "__exit__": lambda *a: None})()
    with patch("urllib.request.urlopen", return_value=resp) as m:
        assert b.trigger("https://x/y.bin", "1.0.0") == 202
        assert m.call_count == 1


def test_trigger_retries_once_on_timeout_then_succeeds(tmp_path, monkeypatch):
    b = _board(tmp_path)
    monkeypatch.setattr("labflash.idf_wifi_ota.TRIGGER_RETRY_PAUSE_S", 0)
    resp = type("R", (), {"status": 202, "__enter__": lambda s: s, "__exit__": lambda *a: None})()
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError(TimeoutError("timed out"))
        return resp

    with patch("urllib.request.urlopen", side_effect=flaky):
        assert b.trigger("https://x/y.bin", "1.0.0") == 202
    assert calls["n"] == 2


def test_trigger_returns_minus_one_after_exhausting_retries(tmp_path, monkeypatch):
    b = _board(tmp_path)
    monkeypatch.setattr("labflash.idf_wifi_ota.TRIGGER_RETRY_PAUSE_S", 0)
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError(TimeoutError("timed out"))) as m:
        assert b.trigger("https://x/y.bin", "1.0.0") == -1
    assert m.call_count == TRIGGER_RETRIES


def test_trigger_http_error_returns_code_without_retry(tmp_path):
    b = _board(tmp_path)
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("u", 401, "no", {}, None)) as m:
        assert b.trigger("https://x/y.bin", "1.0.0") == 401
    assert m.call_count == 1
