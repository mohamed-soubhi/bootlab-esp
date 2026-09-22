import sys
import time
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "host"))

from tools.dashboard.runner import ProcessRunner, JobStatus


def test_runner_executes_simple_job():
    runner = ProcessRunner()
    q = runner.subscribe_events()

    job_id = runner.start_job("doctor", {})
    assert job_id is not None
    assert runner.is_running()

    # Wait for completion
    timeout = 10
    start = time.time()
    events = []
    while runner.is_running() and (time.time() - start < timeout):
        time.sleep(0.1)

    while not q.empty():
        events.append(q.get_nowait())

    runner.unsubscribe_events(q)
    assert not runner.is_running()
    history = runner.get_history()
    assert len(history) >= 1
    assert history[0]["job_id"] == job_id
    assert history[0]["status"] in [JobStatus.PASSED.value, JobStatus.FAILED.value]


def test_runner_enforces_mutex():
    runner = ProcessRunner()
    job_1 = runner.start_job("doctor", {})
    assert runner.is_running()

    with pytest.raises(RuntimeError, match="A job is already running"):
        runner.start_job("doctor", {})

    # Wait for finish
    while runner.is_running():
        time.sleep(0.05)


def test_runner_can_abort_job():
    runner = ProcessRunner()
    # Run a long measure or doctor
    job_id = runner.start_job("measure", {"duration": 10})
    time.sleep(0.2)
    assert runner.is_running()

    aborted = runner.abort_active_job()
    assert aborted is True

    time.sleep(0.5)
    assert not runner.is_running()
    history = runner.get_history()
    assert history[0]["status"] == JobStatus.ABORTED.value


def test_runner_abort_when_not_running():
    runner = ProcessRunner()
    assert runner.abort_active_job() is False


def test_runner_get_active_job():
    runner = ProcessRunner()
    assert runner.get_active_job() is None
    job_id = runner.start_job("measure", {"duration": 10})
    try:
        active = runner.get_active_job()
        assert active is not None
        assert active["job_id"] == job_id
        assert active["tool_id"] == "measure"
    finally:
        runner.abort_active_job()
        time.sleep(0.3)


def test_runner_unsubscribe():
    runner = ProcessRunner()
    q = runner.subscribe_events()
    runner.unsubscribe_events(q)
    runner._broadcast("test", {"msg": "hello"})
    assert q.empty()
