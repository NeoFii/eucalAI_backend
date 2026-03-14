from __future__ import annotations

from scripts.runtime_probe import probe_http_ready


class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.read_called = False

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        self.read_called = True
        return b'{"status":"ready"}'


def test_probe_http_ready_reads_response_body_and_closes_connection(monkeypatch):
    captured: dict[str, object] = {}
    fake_response = _FakeResponse(status=200)

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return fake_response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    ok = probe_http_ready(host="127.0.0.1", port=8001, timeout=1.5)

    assert ok is True
    assert captured["request"].headers["Connection"] == "close"
    assert captured["timeout"] == 1.5
    assert fake_response.read_called is True
