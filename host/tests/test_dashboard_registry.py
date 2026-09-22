import sys
from pathlib import Path
import pytest

# Ensure repo root and host are in PYTHONPATH
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "host"))

from tools.dashboard.tools_registry import (
    TOOLS,
    TOOL_CATEGORIES,
    get_tool,
    build_command,
    detect_boards,
)


def test_tool_catalog_structure():
    assert len(TOOL_CATEGORIES) >= 4
    categories = [c["id"] for c in TOOL_CATEGORIES]
    assert "diagnostics" in categories
    assert "build_flash" in categories
    assert "ota" in categories
    assert "tests" in categories


def test_get_tool():
    tool = get_tool("doctor")
    assert tool is not None
    assert tool.id == "doctor"
    assert tool.category == "diagnostics"

    assert get_tool("nonexistent_tool") is None


def test_build_command_doctor():
    cmd = build_command("doctor", {})
    assert sys.executable in cmd[0]
    assert "-m" in cmd
    assert "labflash" in cmd
    assert "doctor" in cmd


def test_build_command_identify_with_port():
    cmd = build_command("identify", {"port": "COM14"})
    assert "identify" in cmd
    assert "--port" in cmd
    assert "COM14" in cmd


def test_build_command_ota_wifi():
    cmd = build_command("update_wifi", {"variant": "v2", "target": "192.168.1.152"})
    assert "update" in cmd
    assert "--transport" in cmd
    assert "wifi" in cmd
    assert "--variant" in cmd
    assert "v2" in cmd
    assert "--target" in cmd
    assert "192.168.1.152" in cmd


def test_build_command_unknown_tool_raises():
    with pytest.raises(ValueError, match="Unknown tool"):
        build_command("invalid_xyz", {})


def test_detect_boards():
    boards = detect_boards()
    assert isinstance(boards, list)
    network_targets = [b for b in boards if b.get("type") == "network"]
    assert len(network_targets) >= 2

