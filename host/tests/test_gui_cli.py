"""Unit tests for 'labflash gui' CLI subcommand and launcher."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "host"))



def test_labflash_gui_subcommand_registered():
    from labflash.__main__ import build_parser

    parser = build_parser()
    args = parser.parse_args(["gui", "--port", "9090", "--no-browser"])
    assert args.command == "gui"
    assert args.port == 9090
    assert args.no_browser is True
    assert args.host == "127.0.0.1"


def test_labflash_gui_subcommand_defaults():
    from labflash.__main__ import build_parser

    parser = build_parser()
    args = parser.parse_args(["gui"])
    assert args.command == "gui"
    assert args.host == "127.0.0.1"
    assert args.port == 8080
    assert args.no_browser is False


def test_labflash_gui_custom_host():
    from labflash.__main__ import build_parser

    parser = build_parser()
    args = parser.parse_args(["gui", "--host", "0.0.0.0", "--port", "7070"])
    assert args.command == "gui"
    assert args.host == "0.0.0.0"
    assert args.port == 7070
    assert args.no_browser is False


def test_main_dispatches_gui():
    from labflash.__main__ import main

    with patch("labflash.gui_cmd.run_gui", return_value=0) as mock_run:
        rc = main(["gui", "--host", "127.0.0.1", "--port", "8088", "--no-browser"])
        assert rc == 0
        mock_run.assert_called_once_with(host="127.0.0.1", port=8088, open_browser=False)


def test_run_gui_invokes_run_server():
    from labflash.gui_cmd import run_gui

    with patch("tools.dashboard.server.run_server") as mock_server:
        rc = run_gui(host="127.0.0.1", port=8080, open_browser=True)
        assert rc == 0
        mock_server.assert_called_once_with(host="127.0.0.1", port=8080, open_browser=True)


def test_run_gui_handles_server_exception():
    from labflash.gui_cmd import run_gui

    with patch("tools.dashboard.server.run_server", side_effect=OSError("Address already in use")):
        rc = run_gui(host="127.0.0.1", port=8080, open_browser=False)
        assert rc == 1
