"""Unit tests for host/labflash/build.py (BL-045)."""
import subprocess
from pathlib import Path
import pytest

from labflash import build as bld


def test_variant_definitions():
    assert set(bld.IDF_VARIANTS.keys()) == {"v1", "v2", "no_confirm", "hang", "bad_sig"}
    for var, cfg in bld.IDF_VARIANTS.items():
        assert "build_dir" in cfg
        assert "defaults" in cfg
        assert "project_ver" in cfg
        assert "kconfig_sym" in cfg
        assert "signing_key" in cfg


def test_zephyr_is_gated():
    with pytest.raises(bld.ZephyrGatedError, match="Zephyr track is on hold"):
        bld.build_board("zephyr")


def test_unknown_board_rejected():
    with pytest.raises(bld.BuildError, match="Unknown board"):
        bld.build_board("unknown_board")


def test_unknown_variant_rejected():
    with pytest.raises(bld.BuildError, match="Unknown IDF variant"):
        bld.build_idf_variant("invalid_var")


def test_verify_sdkconfig_variant(tmp_path):
    cfg_file = tmp_path / "sdkconfig"
    cfg_file.write_text("CONFIG_APP_VARIANT_V1=y\nCONFIG_IDF_TARGET=\"esp32s3\"\n")
    assert bld.verify_sdkconfig_variant(cfg_file, "CONFIG_APP_VARIANT_V1=y")
    assert not bld.verify_sdkconfig_variant(cfg_file, "CONFIG_APP_VARIANT_V2=y")
    assert not bld.verify_sdkconfig_variant(tmp_path / "nonexistent", "CONFIG_APP_VARIANT_V1=y")


def test_stale_sdkconfig_removed(tmp_path):
    esp_idf = tmp_path / "esp_idf"
    esp_idf.mkdir(parents=True)
    stale = esp_idf / "sdkconfig"
    stale.write_text("STALE")
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "idf_sbv2.pem").write_text("DUMMY_KEY")

    build_dir = esp_idf / "build"

    def mock_runner(cmd, cwd=None):
        # Fake successful build output
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "sdkconfig").write_text("CONFIG_APP_VARIANT_V1=y\n")
        (build_dir / bld.BINARY_NAME).write_bytes(b"\xE9" + b"\x00" * 1024)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="OK", stderr="")

    res = bld.build_idf_variant("v1", repo_root=tmp_path, runner=mock_runner)
    assert not stale.exists()
    assert res.variant == "v1"
    assert res.verified_variant
    assert res.verified_signature


def test_bad_sig_verification_logic(tmp_path):
    esp_idf = tmp_path / "esp_idf"
    esp_idf.mkdir(parents=True)
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "idf_sbv2.pem").write_text("KEY1")
    (tmp_path / "keys" / "idf_foreign.pem").write_text("KEY2")

    build_dir = esp_idf / "build_bad_sig"

    # Case 1: bad_sig passes primary key verification -> MUST raise error!
    def mock_runner_insecure(cmd, cwd=None):
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "sdkconfig").write_text("CONFIG_APP_VARIANT_BAD_SIG=y\n")
        (build_dir / bld.BINARY_NAME).write_bytes(b"\xE9" + b"\x00" * 1024)
        # returncode 0 means signature passed
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="OK", stderr="")

    with pytest.raises(bld.BuildError, match="Security check failed: bad_sig was unexpectedly accepted"):
        bld.build_idf_variant("bad_sig", repo_root=tmp_path, runner=mock_runner_insecure)

    # Case 2: bad_sig fails primary key verification, passes foreign key -> SUCCESS!
    def mock_runner_correct(cmd, cwd=None):
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "sdkconfig").write_text("CONFIG_APP_VARIANT_BAD_SIG=y\n")
        (build_dir / bld.BINARY_NAME).write_bytes(b"\xE9" + b"\x00" * 1024)
        if "verify-signature" in cmd or "verify_signature" in cmd:
            # If checking with primary key -> return 1 (fail)
            if "idf_sbv2.pem" in str(cmd):
                return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="Signature invalid")
            # If checking with foreign key -> return 0 (pass)
            if "idf_foreign.pem" in str(cmd):
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Valid", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="OK", stderr="")

    res = bld.build_idf_variant("bad_sig", repo_root=tmp_path, runner=mock_runner_correct)
    assert res.variant == "bad_sig"
    assert res.verified_variant
    assert res.verified_signature
