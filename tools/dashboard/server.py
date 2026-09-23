"""Lightweight HTTP server with Server-Sent Events broker for the Operations Console."""

from __future__ import annotations

import argparse
import http.server
import json
import queue
import socketserver
import sys
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
HOST_DIR = REPO_ROOT / "host"
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from tools.dashboard.runner import ProcessRunner
from tools.dashboard.tools_registry import (
    TOOL_CATEGORIES,
    TOOLS,
    detect_boards,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
GLOBAL_RUNNER = ProcessRunner()


class DashboardServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[http.server.BaseHTTPRequestHandler],
        runner: ProcessRunner | None = None,
        bind_and_activate: bool = True,
    ) -> None:
        self.runner = runner or GLOBAL_RUNNER
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc = sys.exception()
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError)):
            return
        super().handle_error(request, client_address)


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def handle(self) -> None:
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    @property
    def runner(self) -> ProcessRunner:
        if hasattr(self.server, "runner") and getattr(self.server, "runner") is not None:
            return getattr(self.server, "runner")
        return GLOBAL_RUNNER

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_path = urllib.parse.urlparse(self.path).path
        if parsed_path in ("/", "/index.html"):
            return self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif parsed_path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        elif parsed_path == "/style.css":
            return self._serve_file(STATIC_DIR / "style.css", "text/css; charset=utf-8")
        elif parsed_path == "/app.js":
            return self._serve_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
        elif parsed_path == "/api/tools":
            return self._send_json({
                "categories": TOOL_CATEGORIES,
                "tools": {
                    k: {
                        "id": v.id,
                        "name": v.name,
                        "category": v.category,
                        "description": v.description,
                        "safety_level": v.safety_level,
                        "parameters": [
                            {
                                "name": p.name,
                                "label": p.label,
                                "type": p.param_type,
                                "default": p.default,
                                "options": list(p.options),
                                "description": p.description,
                                "required": p.required,
                            }
                            for p in v.parameters
                        ],
                    }
                    for k, v in TOOLS.items()
                },
            })
        elif parsed_path == "/api/boards":
            return self._send_json({"boards": detect_boards()})
        elif parsed_path == "/api/history":
            return self._send_json({
                "history": self.runner.get_history(),
                "active_job": self.runner.get_active_job(),
            })
        elif parsed_path == "/api/stream":
            return self._handle_sse_stream()
        else:
            return super().do_GET()

    def do_POST(self) -> None:
        parsed_path = urllib.parse.urlparse(self.path).path
        if parsed_path == "/api/run":
            body = self._read_json_body()
            tool_id = body.get("tool_id")
            params = body.get("params", {})

            if not tool_id:
                return self._send_error_json("Missing 'tool_id' parameter", 400)

            try:
                job_id = self.runner.start_job(tool_id, params)
                return self._send_json({"job_id": job_id, "status": "running"})
            except RuntimeError as e:
                return self._send_error_json(str(e), 409)
            except ValueError as e:
                return self._send_error_json(str(e), 400)
            except Exception as e:
                return self._send_error_json(str(e), 500)

        elif parsed_path == "/api/abort":
            aborted = self.runner.abort_active_job()
            return self._send_json({"aborted": aborted})
        else:
            self.send_error(404, "Endpoint not found")

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(404, f"File not found: {path.name}")
            return
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int) -> None:
        self._send_json({"error": message}, status=status)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _handle_sse_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        event_queue = self.runner.subscribe_events()
        try:
            # Send initial keep-alive
            self.wfile.write(b": keep-alive\n\n")
            self.wfile.flush()

            while True:
                try:
                    payload = event_queue.get(timeout=1.0)
                    evt = payload.get("event", "message")
                    data = json.dumps(payload.get("data", {}))
                    msg = f"event: {evt}\ndata: {data}\n\n".encode("utf-8")
                    self.wfile.write(msg)
                    self.wfile.flush()
                except queue.Empty:
                    # Keep-alive comment
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            self.runner.unsubscribe_events(event_queue)


def make_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    runner: ProcessRunner | None = None,
) -> DashboardServer:
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    return DashboardServer((host, port), DashboardRequestHandler, runner=runner)


def run_server(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    server = make_server(host=host, port=port)
    url = f"http://{host}:{port}"
    print(f"\n=======================================================")
    print(f" ⚡ bootlab-esp Operations Console")
    print(f" Listening on: {url}")
    print(f" Press Ctrl+C to stop.")
    print(f"=======================================================\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Shutting down Operations Console...")
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="bootlab-esp Operations Console")
    parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)
