import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "host"))

from tools.dashboard.server import make_server, GLOBAL_RUNNER


@pytest.fixture(scope="module")
def server_url():
    server = make_server(host="127.0.0.1", port=8989)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    yield "http://127.0.0.1:8989"
    server.shutdown()
    server.server_close()


def test_get_root_serves_html(server_url):
    req = urllib.request.Request(f"{server_url}/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "<title>" in content or "bootlab-esp" in content


def test_get_tools_endpoint(server_url):
    req = urllib.request.Request(f"{server_url}/api/tools")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "categories" in data
        assert "tools" in data
        assert len(data["tools"]) >= 5


def test_get_boards_endpoint(server_url):
    req = urllib.request.Request(f"{server_url}/api/boards")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "boards" in data
        assert isinstance(data["boards"], list)


def test_run_and_history_lifecycle(server_url):
    # Wait for any previous job to finish
    timeout = 10
    start = time.time()
    while GLOBAL_RUNNER.is_running() and (time.time() - start < timeout):
        time.sleep(0.1)

    payload = json.dumps({"tool_id": "doctor", "params": {}}).encode("utf-8")
    req = urllib.request.Request(
        f"{server_url}/api/run",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "job_id" in data
        assert data.get("status") == "running"
        job_id = data["job_id"]

    # Wait for completion and check history
    start = time.time()
    while GLOBAL_RUNNER.is_running() and (time.time() - start < timeout):
        time.sleep(0.1)

    req_hist = urllib.request.Request(f"{server_url}/api/history")
    with urllib.request.urlopen(req_hist) as resp:
        hist_data = json.loads(resp.read().decode("utf-8"))
        assert "history" in hist_data
        assert any(j["job_id"] == job_id for j in hist_data["history"])


def test_run_missing_tool_id(server_url):
    payload = json.dumps({"params": {}}).encode("utf-8")
    req = urllib.request.Request(
        f"{server_url}/api/run",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 400


def test_run_conflict_409(server_url):
    # Ensure no job is running
    while GLOBAL_RUNNER.is_running():
        time.sleep(0.1)

    # Start a longer job
    payload = json.dumps({"tool_id": "measure", "params": {"duration": 10}}).encode("utf-8")
    req1 = urllib.request.Request(
        f"{server_url}/api/run",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req1) as resp1:
        assert resp1.status == 200

    # Attempt starting another job concurrently -> should get 409 Conflict
    req2 = urllib.request.Request(
        f"{server_url}/api/run",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req2)
    assert exc_info.value.code == 409

    # Abort the active job
    req_abort = urllib.request.Request(
        f"{server_url}/api/abort",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req_abort) as resp_abort:
        assert resp_abort.status == 200
        abort_data = json.loads(resp_abort.read().decode("utf-8"))
        assert abort_data["aborted"] is True

    # Wait for abort to clean up
    time.sleep(0.5)


def test_abort_endpoint_when_idle(server_url):
    while GLOBAL_RUNNER.is_running():
        time.sleep(0.1)

    req = urllib.request.Request(
        f"{server_url}/api/abort",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["aborted"] is False


def test_sse_stream_endpoint(server_url):
    req = urllib.request.Request(f"{server_url}/api/stream")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        assert "text/event-stream" in resp.headers.get("Content-Type", "")
        # Read the first chunk (initial keep-alive)
        first_line = resp.readline().decode("utf-8")
        assert ": keep-alive" in first_line
