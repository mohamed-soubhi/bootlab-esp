"""GUI subcommand integration for labflash."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def run_gui(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> int:
    """Launch the bootlab-esp Operations Console."""
    # Ensure repository root is on sys.path so tools.dashboard can be imported
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    try:
        from tools.dashboard.server import run_server

        run_server(host=host, port=port, open_browser=open_browser)
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to start Operations Console: {e}", file=sys.stderr)
        return 1
