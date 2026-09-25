"""Unit tests for host/labflash/build.py (BL-045)."""
import subprocess
from unittest.mock import patch

import pytest
from labflash import build as bld


def test_variant_definitions():
    assert set(bld.IDF_VARIANTS.keys()) == {"v1", "v2", "no_confirm", "hang", "bad_sig"}
    for cfg in bld.IDF_VARIANTS.values():
        assert "build_dir" in cfg
        assert "defaults" in cfg
        assert "project_ver" in cfg
        assert "kconfig_sym" in cfg
        assert "signing_key" in cfg


def test_zephyr_variant_definitions():
    assert set(bld.ZEPHYR_VARIANTS.keys()) == {"v1", "v2", "no_confirm", "hang", "bad_sig"}
    for cfg in bld.ZEPHYR_VARIANTS.values():
        assert "build_dir" in cfg
        assert "overlay" in cfg
        assert "project_ver" in cfg
        assert "kconfig_sym" in cfg
        assert "expected_sig_valid" in cfg


def test_unknown_board_rejected():
    with pytest.raises(bld.BuildError, match="Unknown board"):
        bld.build_board("unknown_board")


def test_unknown_variant_rejected():
    with pytest.raises(bld.BuildError, match="Unknown IDF variant"):
        bld.build_idf_variant("invalid_var")
    with pytest.raises(bld.BuildError, match="Unknown Zephyr variant"):
        bld.build_zephyr_variant("invalid_var")


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


def test_stale_sdkconfig_and_clean(tmp_path):
    esp_idf = tmp_path / "esp_idf"
    bdir = esp_idf / "build"
    bdir.mkdir(parents=True)
    (bdir / "dummy.bin").write_bytes(b"dummy")
    stale = esp_idf / "sdkconfig"
    stale.write_text("STALE")

    def mock_runner(cmd, cwd=None):
        if "generate_signing_key" in cmd or "generate-signing-key" in cmd:
            (tmp_path / "keys" / "idf_sbv2.pem").write_bytes(b"MOCK KEY")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="OK", stderr="")
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "sdkconfig").write_text("CONFIG_APP_VARIANT_V1=y\n")
        (bdir / bld.BINARY_NAME).write_bytes(b"\xE9" + b"\x00" * 1024)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="OK", stderr="")

    res = bld.build_idf_variant("v1", repo_root=tmp_path, clean=True, runner=mock_runner)
    assert not stale.exists()
    assert res.variant == "v1"


def test_build_board_dispatch(tmp_path):
    # Test invalid board name
    with pytest.raises(bld.BuildError, match="Unknown board 'unknown'"):
        bld.build_board("unknown", repo_root=tmp_path)

    # Test build_board for single variant
    fake_res = bld.BuildResult(
        board="idf",
        variant="v1",
        build_dir=tmp_path / "build",
        binary_path=tmp_path / "build" / "app.bin",
        binary_size=100,
        project_ver="1.0.0",
        verified_variant=True,
        verified_signature=True,
    )
    fake_zephyr_res = bld.BuildResult(
        board="zephyr",
        variant="v1",
        build_dir=tmp_path / "build_v1",
        binary_path=tmp_path / "build_v1" / "app" / "zephyr" / "zephyr.signed.bin",
        binary_size=200,
        project_ver="1.0.0",
        verified_variant=True,
        verified_signature=True,
    )
    with patch("labflash.build.build_idf_variant", return_value=fake_res):
        res = bld.build_board("idf", variant="v1", repo_root=tmp_path)
        assert "v1" in res
        assert res["v1"] == fake_res

    with patch("labflash.build.build_zephyr_variant", return_value=fake_zephyr_res):
        res = bld.build_board("zephyr", variant="v1", repo_root=tmp_path)
        assert "v1" in res
        assert res["v1"] == fake_zephyr_res

    # Test build_board for all variants
    with patch("labflash.build.build_idf_all", return_value={"v1": fake_res}), \
         patch("labflash.build.build_zephyr_all", return_value={"v1": fake_zephyr_res}):
        res_idf_all = bld.build_board("idf", variant="all", repo_root=tmp_path)
        assert res_idf_all == {"v1": fake_res}

        res_zephyr_all = bld.build_board("zephyr", variant="all", repo_root=tmp_path)
        assert res_zephyr_all == {"v1": fake_zephyr_res}

        # Test board == "all"
        res_board_all = bld.build_board("all", repo_root=tmp_path)
        assert "v1" in res_board_all


def test_find_idf_export_script(tmp_path, monkeypatch):
    fake_idf = tmp_path / "esp-idf"
    fake_idf.mkdir()
    export_sh = fake_idf / "export.sh"
    export_sh.write_text("#!/bin/bash\n")

    monkeypatch.setenv("IDF_PATH", str(fake_idf))
    found = bld.find_idf_export_script()
    assert found == export_sh


def test_run_command_mocked(tmp_path):
    proc = subprocess.CompletedProcess(args=["echo", "hi"], returncode=0, stdout="hi\n", stderr="")
    with patch("subprocess.run", return_value=proc):
        r = bld.run_command(["echo", "hi"], cwd=tmp_path)
        assert r.returncode == 0


def test_ensure_keys_both(tmp_path):
    def mock_runner(cmd, cwd=None):
        if "idf_sbv2.pem" in str(cmd):
            (tmp_path / "keys" / "idf_sbv2.pem").write_bytes(b"KEY1")
        if "idf_foreign.pem" in str(cmd):
            (tmp_path / "keys" / "idf_foreign.pem").write_bytes(b"KEY2")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    bld.ensure_keys(tmp_path, need_foreign=True, runner=mock_runner)
    assert (tmp_path / "keys" / "idf_sbv2.pem").exists()
    assert (tmp_path / "keys" / "idf_foreign.pem").exists()


def test_verify_sdkconfig_variant_edge_cases(tmp_path):
    conf = tmp_path / "sdkconfig"
    assert bld.verify_sdkconfig_variant(conf, "CONFIG_V1=y") is False
    conf.write_text("CONFIG_V1=y\n")
    assert bld.verify_sdkconfig_variant(conf, "CONFIG_V1=y") is True
    assert bld.verify_sdkconfig_variant(conf, "CONFIG_V2=y") is False


def test_build_idf_variant_build_failure(tmp_path):
    (tmp_path / "keys" / "idf_sbv2.pem").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "keys" / "idf_sbv2.pem").write_bytes(b"KEY")

    def failing_runner(cmd, cwd=None):
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="Compilation error")

    with pytest.raises(bld.BuildError, match="Build failed for variant 'v1'"):
        bld.build_idf_variant("v1", repo_root=tmp_path, runner=failing_runner)


def test_build_zephyr_variant_mocked(tmp_path):
    (tmp_path / "keys").mkdir(parents=True, exist_ok=True)
    (tmp_path / "keys" / "zephyr_p256.pem").write_bytes(b"ZEPHYR_KEY")

    build_dir = tmp_path / "esp_zephyr" / "app" / "build_v1"
    app_zephyr = build_dir / "app" / "zephyr"

    def mock_runner(cmd, cwd=None, env=None):
        app_zephyr.mkdir(parents=True, exist_ok=True)
        (app_zephyr / ".config").write_text("CONFIG_APP_VARIANT_V1=y\n")
        (app_zephyr / "zephyr.signed.bin").write_bytes(b"SIGNED_BIN_DATA")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="West build OK", stderr="")

    res = bld.build_zephyr_variant("v1", repo_root=tmp_path, runner=mock_runner)
    assert res.board == "zephyr"
    assert res.variant == "v1"
    assert res.verified_variant
    assert res.verified_signature


def test_build_zephyr_bad_sig_mocked(tmp_path):
    (tmp_path / "keys").mkdir(parents=True, exist_ok=True)
    (tmp_path / "keys" / "zephyr_p256.pem").write_bytes(b"ZEPHYR_KEY")
    (tmp_path / "keys" / "zephyr_foreign.pem").write_bytes(b"FOREIGN_KEY")

    build_dir = tmp_path / "esp_zephyr" / "app" / "build_bad_sig"
    app_zephyr = build_dir / "app" / "zephyr"

    def mock_runner(cmd, cwd=None, env=None):
        app_zephyr.mkdir(parents=True, exist_ok=True)
        (app_zephyr / ".config").write_text("CONFIG_APP_VARIANT_BAD_SIG=y\n")
        (app_zephyr / "zephyr.signed.bin").write_bytes(b"BAD_SIG_BIN_DATA")
        if "verify" in cmd:
            if "zephyr_p256.pem" in str(cmd):
                return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="Bad sig")
            if "zephyr_foreign.pem" in str(cmd):
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Foreign valid", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="West build OK", stderr="")

    res = bld.build_zephyr_variant("bad_sig", repo_root=tmp_path, runner=mock_runner)
    assert res.variant == "bad_sig"
    assert res.verified_signature
    assert "refused by primary key" in res.details




def _fake_idf(tmp_path, cmds):
    (tmp_path / "esp_idf").mkdir(parents=True, exist_ok=True)
    (tmp_path / "keys").mkdir(exist_ok=True)
    (tmp_path / "keys" / "idf_sbv2.pem").write_text("K")

    def runner(cmd, cwd=None):
        cmds.append(list(cmd))
        if cmd[0] == "idf.py":
            b = next(a for i, a in enumerate(cmd) if cmd[i - 1] == "-B")
            from pathlib import Path
            Path(b).mkdir(parents=True, exist_ok=True)
            (Path(b) / "sdkconfig").write_text("CONFIG_APP_VARIANT_V1=y\nCONFIG_APP_GEN_POOL=y\n")
            (Path(b) / bld.BINARY_NAME).write_bytes(b"\xE9" + b"\0" * 4095)
        return subprocess.CompletedProcess(cmd, 0, "OK", "")
    return runner


def test_build_idf_image_passes_build_dir_version_defaults_and_extra_defs(tmp_path):
    cmds: list = []
    out = tmp_path / "esp_idf" / "build_pool" / "g00"
    res = bld.build_idf_image(
        build_dir=out, project_ver="gen-0000abcd",
        defaults="sdkconfig.defaults;/abs/pool.defaults",
        kconfig_sym="CONFIG_APP_VARIANT_V1=y", repo_root=tmp_path,
        runner=_fake_idf(tmp_path, cmds), extra_cmake_defs=("-DGEN_PAD_FILE=/abs/pad.bin",), label="g00",
    )
    build_cmd = next(c for c in cmds if c[0] == "idf.py")
    assert str(out) in build_cmd and "-DPROJECT_VER=gen-0000abcd" in build_cmd
    assert "-DSDKCONFIG_DEFAULTS=sdkconfig.defaults;/abs/pool.defaults" in build_cmd
    assert "-DGEN_PAD_FILE=/abs/pad.bin" in build_cmd and build_cmd[-1] == "build"
    assert res.variant == "g00" and res.build_dir == out and res.project_ver == "gen-0000abcd"
    assert res.verified_signature


def test_build_idf_image_still_runs_the_three_gates(tmp_path):
    cmds: list = []
    good = _fake_idf(tmp_path, cmds)

    def wrong_symbol(cmd, cwd=None):
        r = good(cmd, cwd)
        if cmd[0] == "idf.py":
            (tmp_path / "esp_idf" / "b" / "sdkconfig").write_text("nothing\n")
        return r
    with pytest.raises(bld.BuildError, match="Variant verification failed"):
        bld.build_idf_image(build_dir=tmp_path / "esp_idf" / "b", project_ver="x", defaults="d",
                            kconfig_sym="CONFIG_APP_VARIANT_V1=y", repo_root=tmp_path, runner=wrong_symbol)

    def bad_sig(cmd, cwd=None):
        r = good(cmd, cwd)
        return subprocess.CompletedProcess(cmd, 1, "", "invalid") if cmd[0].startswith("espsecure") else r
    with pytest.raises(bld.BuildError, match="Signature verification FAILED"):
        bld.build_idf_image(build_dir=tmp_path / "esp_idf" / "b2", project_ver="x", defaults="d",
                            kconfig_sym="CONFIG_APP_VARIANT_V1=y", repo_root=tmp_path, runner=bad_sig)


def test_build_idf_variant_command_is_unchanged_by_the_refactor(tmp_path):
    cmds: list = []
    bld.build_idf_variant("v1", repo_root=tmp_path, runner=_fake_idf(tmp_path, cmds))
    build_cmd = next(c for c in cmds if c[0] == "idf.py")
    esp = tmp_path / "esp_idf"
    assert build_cmd == ["idf.py", "-C", str(esp), "-B", str(esp / "build"),
                         f"-DSDKCONFIG={esp / 'build' / 'sdkconfig'}",
                         "-DSDKCONFIG_DEFAULTS=sdkconfig.defaults", "-DPROJECT_VER=1.0.0", "build"]
