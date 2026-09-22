"""Subprocess execution engine with concurrency lock and streaming event dispatch."""

from __future__ import annotations

import enum
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from tools.dashboard.tools_registry import build_command, get_tool

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ABORTED = "aborted"


class ProcessRunner:
    def __init__(self, cwd: Path | None = None) -> None:
        self._cwd = cwd or REPO_ROOT
        self._lock = threading.Lock()
        self._active_proc: subprocess.Popen | None = None
        self._active_job: dict[str, Any] | None = None
        self._history: list[dict[str, Any]] = []
        self._subscribers: list[queue.Queue] = []
        self._subscribers_lock = threading.Lock()

    def is_running(self) -> bool:
        with self._lock:
            return self._active_proc is not None and self._active_proc.poll() is None

    def get_active_job(self) -> dict[str, Any] | None:
        with self._lock:
            if self._active_job and self._active_proc is not None and self._active_proc.poll() is None:
                return dict(self._active_job)
            return None

    def get_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history)

    def subscribe_events(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe_events(self, q: queue.Queue) -> None:
        with self._subscribers_lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        payload = {"event": event_type, "data": data, "timestamp": time.time()}
        with self._subscribers_lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    pass

    def start_job(self, tool_id: str, params: dict[str, Any]) -> str:
        with self._lock:
            if self._active_proc is not None and self._active_proc.poll() is None:
                raise RuntimeError("A job is already running. Please wait or cancel the active job.")

            cmd = build_command(tool_id, params)
            tool = get_tool(tool_id)
            tool_name = tool.name if tool else tool_id

            # Normalize measure command if invoked without board or using duration alias
            if len(cmd) >= 4 and cmd[1:4] == ["-m", "labflash", "measure"]:
                board = params.get("board", "idf")
                if not any(b in cmd[4:] for b in ("idf", "zephyr")):
                    cmd.insert(4, board)
                if "--duration" in cmd:
                    d_idx = cmd.index("--duration")
                    cmd[d_idx] = "--seconds"

            job_id = f"job-{int(time.time() * 1000)}"
            start_time = time.time()

            # Set execution environment with PYTHONPATH
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{self._cwd / 'host'}:{self._cwd}:{env.get('PYTHONPATH', '')}"
            env["PYTHONUNBUFFERED"] = "1"

            # Preexec for process group creation on POSIX
            kwargs: dict[str, Any] = {
                "cwd": str(self._cwd),
                "env": env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "bufsize": 1,
            }
            if sys.platform != "win32":
                kwargs["start_new_session"] = True
            else:
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

            try:
                proc = subprocess.Popen(cmd, **kwargs)
            except Exception as e:
                self._broadcast("status", {
                    "job_id": job_id,
                    "status": JobStatus.FAILED.value,
                    "error": str(e),
                })
                raise

            job_info = {
                "job_id": job_id,
                "tool_id": tool_id,
                "tool_name": tool_name,
                "cmd": cmd,
                "cmd_str": " ".join(cmd),
                "params": params,
                "status": JobStatus.RUNNING.value,
                "start_time": start_time,
                "end_time": None,
                "exit_code": None,
                "output_lines": [],
            }

            self._active_proc = proc
            self._active_job = job_info

            # Start background reader thread
            t = threading.Thread(
                target=self._reader_loop,
                args=(proc, job_id, start_time),
                daemon=True,
            )
            t.start()

            self._broadcast("status", {
                "job_id": job_id,
                "tool_name": tool_name,
                "cmd": " ".join(cmd),
                "status": JobStatus.RUNNING.value,
            })

            return job_id

    def _reader_loop(self, proc: subprocess.Popen, job_id: str, start_time: float) -> None:
        output_lines: list[str] = []
        try:
            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    elapsed = round(time.time() - start_time, 2)
                    output_lines.append(line)
                    self._broadcast("log", {
                        "job_id": job_id,
                        "line": line,
                        "elapsed": elapsed,
                    })
        except Exception:
            pass
        finally:
            exit_code = proc.wait()
            end_time = time.time()
            elapsed = round(end_time - start_time, 2)

            with self._lock:
                status = JobStatus.PASSED.value if exit_code == 0 else JobStatus.FAILED.value
                if self._active_job and self._active_job.get("status") == JobStatus.ABORTED.value:
                    status = JobStatus.ABORTED.value

                if self._active_job and self._active_job.get("job_id") == job_id:
                    self._active_job["status"] = status
                    self._active_job["exit_code"] = exit_code
                    self._active_job["end_time"] = end_time
                    self._active_job["elapsed"] = elapsed
                    self._active_job["output_lines"] = output_lines
                    self._history.insert(0, dict(self._active_job))
                    # Retain last 20 jobs
                    self._history = self._history[:20]

                    self._active_proc = None

            self._broadcast("status", {
                "job_id": job_id,
                "status": status,
                "exit_code": exit_code,
                "elapsed": elapsed,
            })

    def abort_active_job(self) -> bool:
        with self._lock:
            if self._active_proc is None or self._active_proc.poll() is not None:
                return False

            proc = self._active_proc
            if self._active_job:
                self._active_job["status"] = JobStatus.ABORTED.value

        try:
            if sys.platform != "win32":
                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            else:
                proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

        # Give it up to 2 seconds to release port before killing
        def _force_kill():
            time.sleep(2.0)
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

        threading.Thread(target=_force_kill, daemon=True).start()
        return True
