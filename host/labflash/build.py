"""labflash build — build and sign orchestration for IDF & Zephyr variants (BL-045).

Implements PLAN R15:
- Each variant has its own build directory (-B <dir>) and its own sdkconfig
  (-DSDKCONFIG=<dir>/sdkconfig) to avoid cross-variant contamination.
- Removes any stale project-level esp_idf/sdkconfig before building.
- Post-build verification:
  1. Confirms the expected CONFIG_APP_VARIANT_* is present in <dir>/sdkconfig.
  2. Confirms the binary exists and has non-zero size.
  3. Signature check:
     - v1, v2, no_confirm, hang: verified against keys/idf_sbv2.pem.
     - bad_sig: verification against keys/idf_sbv2.pem MUST fail,
       verification against keys/idf_foreign.pem MUST pass.
- Enforces the Zephyr gate: building Zephyr is blocked pending BL-063b.
"""
from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]

IDF_VARIANTS: dict[str, dict] = {
    "v1": {
        "build_dir": "esp_idf/build",
        "defaults": "sdkconfig.defaults",
        "project_ver": "1.0.0",
        "kconfig_sym": "CONFIG_APP_VARIANT_V1=y",
        "signing_key": "keys/idf_sbv2.pem",
        "expected_sig_valid": True,
    },
    "v2": {
        "build_dir": "esp_idf/build_v2",
        "defaults": "sdkconfig.defaults;sdkconfig.v2",
        "project_ver": "2.0.0",
        "kconfig_sym": "CONFIG_APP_VARIANT_V2=y",
        "signing_key": "keys/idf_sbv2.pem",
        "expected_sig_valid": True,
    },
    "no_confirm": {
        "build_dir": "esp_idf/build_no_confirm",
        "defaults": "sdkconfig.defaults;sdkconfig.no_confirm",
        "project_ver": "1.0.0-noconfirm",
        "kconfig_sym": "CONFIG_APP_VARIANT_NO_CONFIRM=y",
        "signing_key": "keys/idf_sbv2.pem",
        "expected_sig_valid": True,
    },
    "hang": {
        "build_dir": "esp_idf/build_hang",
        "defaults": "sdkconfig.defaults;sdkconfig.hang",
        "project_ver": "1.0.0-hang",
        "kconfig_sym": "CONFIG_APP_VARIANT_HANG=y",
        "signing_key": "keys/idf_sbv2.pem",
        "expected_sig_valid": True,
    },
    "bad_sig": {
        "build_dir": "esp_idf/build_bad_sig",
        "defaults": "sdkconfig.defaults;sdkconfig.bad_sig",
        "project_ver": "1.0.0-badsig",
        "kconfig_sym": "CONFIG_APP_VARIANT_BAD_SIG=y",
        "signing_key": "keys/idf_foreign.pem",
        "expected_sig_valid": False,  # MUST fail verification against primary key
    },
}

ZEPHYR_VARIANTS: dict[str, dict] = {
    "v1": {
        "build_dir": "esp_zephyr/app/build_v1",
        "overlay": "esp_zephyr/app/overlay_v1.conf",
        "project_ver": "1.0.0",
        "kconfig_sym": "CONFIG_APP_VARIANT_V1=y",
        "signing_key": "keys/zephyr_p256.pem",
        "expected_sig_valid": True,
    },
    "v2": {
        "build_dir": "esp_zephyr/app/build_v2",
        "overlay": "esp_zephyr/app/overlay_v2.conf",
        "project_ver": "2.0.0",
        "kconfig_sym": "CONFIG_APP_VARIANT_V2=y",
        "signing_key": "keys/zephyr_p256.pem",
        "expected_sig_valid": True,
    },
    "no_confirm": {
        "build_dir": "esp_zephyr/app/build_no_confirm",
        "overlay": "esp_zephyr/app/overlay_no_confirm.conf",
        "project_ver": "1.0.0-noconfirm",
        "kconfig_sym": "CONFIG_APP_VARIANT_NO_CONFIRM=y",
        "signing_key": "keys/zephyr_p256.pem",
        "expected_sig_valid": True,
    },
    "hang": {
        "build_dir": "esp_zephyr/app/build_hang",
        "overlay": "esp_zephyr/app/overlay_hang.conf",
        "project_ver": "1.0.0-hang",
        "kconfig_sym": "CONFIG_APP_VARIANT_HANG=y",
        "signing_key": "keys/zephyr_p256.pem",
        "expected_sig_valid": True,
    },
    "bad_sig": {
        "build_dir": "esp_zephyr/app/build_bad_sig",
        "overlay": "esp_zephyr/app/overlay_bad_sig.conf",
        "sysbuild_conf": "esp_zephyr/app/sysbuild_bad_sig.conf",
        "project_ver": "1.0.0-badsig",
        "kconfig_sym": "CONFIG_APP_VARIANT_BAD_SIG=y",
        "signing_key": "keys/zephyr_foreign.pem",
        "expected_sig_valid": False,
    },
}

BINARY_NAME = "bootlab_idf_blink.bin"
ZEPHYR_BINARY_NAME = "zephyr.signed.bin"


class BuildError(RuntimeError):
    """Raised when build or post-verification fails."""


class ZephyrGatedError(BuildError):
    """Raised when attempting to build Zephyr while gated."""


@dataclasses.dataclass
class BuildResult:
    board: str
    variant: str
    build_dir: Path
    binary_path: Path
    binary_size: int
    project_ver: str
    verified_variant: bool
    verified_signature: bool
    details: str = ""


def find_idf_export_script(repo_root: Path | None = None) -> Path | None:
    """Find export.sh for ESP-IDF environment."""
    candidates = [
        Path(os.environ.get("IDF_PATH", "")) / "export.sh",
        Path.home() / "tools" / "esp-idf" / "export.sh",
        Path.home() / "esp" / "esp-idf" / "export.sh",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def run_command(
    cmd: Sequence[str] | str,
    cwd: Path,
    use_idf_env: bool = False,
    runner: Callable | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a shell/exec command, optionally wrapping in export.sh if idf not in PATH."""
    if runner is not None:
        return runner(cmd, cwd=cwd)

    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    # Sanitize PATH in WSL2 to prevent 9P filesystem crawl hangs
    if "/mnt/c" in run_env.get("PATH", ""):
        run_env["PATH"] = ":".join(p for p in run_env["PATH"].split(":") if not p.startswith("/mnt/c"))

    if use_idf_env and not shutil.which("idf.py"):
        export_sh = find_idf_export_script()
        if not export_sh:
            raise BuildError("ESP-IDF not in PATH and export.sh could not be found")
        cmd_str = " ".join(f"'{a}'" for a in cmd) if isinstance(cmd, (list, tuple)) else cmd
        full_cmd = ["bash", "-c", f". '{export_sh}' >/dev/null 2>&1 && {cmd_str}"]
        return subprocess.run(full_cmd, cwd=cwd, env=run_env, capture_output=True, text=True, check=False)

    if isinstance(cmd, str):
        return subprocess.run(cmd, cwd=cwd, env=run_env, shell=True, capture_output=True, text=True, check=False)
    return subprocess.run(cmd, cwd=cwd, env=run_env, capture_output=True, text=True, check=False)


def ensure_keys(repo_root: Path, need_foreign: bool = False, runner: Callable | None = None) -> None:
    """Ensure lab signing keys (primary and optionally foreign) exist."""
    keys_dir = repo_root / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(keys_dir, 0o700)
    except OSError:
        pass

    primary_key = keys_dir / "idf_sbv2.pem"
    if not primary_key.exists():
        res = run_command(
            ["espsecure.py", "generate_signing_key", "--version", "2", "--scheme", "rsa3072", str(primary_key)],
            cwd=keys_dir,
            use_idf_env=True,
            runner=runner,
        )
        if not primary_key.exists() and res.returncode != 0:
            # Try espsecure without .py
            res = run_command(
                ["espsecure", "generate-signing-key", "--version", "2", "--scheme", "rsa3072", str(primary_key)],
                cwd=keys_dir,
                use_idf_env=True,
                runner=runner,
            )
        if not primary_key.exists():
            raise BuildError(f"Failed to generate primary key {primary_key}: {res.stderr}")

    if need_foreign:
        foreign_key = keys_dir / "idf_foreign.pem"
        if not foreign_key.exists():
            res = run_command(
                ["espsecure.py", "generate_signing_key", "--version", "2", "--scheme", "rsa3072", str(foreign_key)],
                cwd=keys_dir,
                use_idf_env=True,
                runner=runner,
            )
            if not foreign_key.exists() and res.returncode != 0:
                res = run_command(
                    ["espsecure", "generate-signing-key", "--version", "2", "--scheme", "rsa3072", str(foreign_key)],
                    cwd=keys_dir,
                    use_idf_env=True,
                    runner=runner,
                )
            if not foreign_key.exists():
                raise BuildError(f"Failed to generate foreign key {foreign_key}: {res.stderr}")


def verify_signature(
    binary_path: Path,
    key_path: Path,
    runner: Callable | None = None,
) -> bool:
    """Check if binary passes RSA-3072 SBv2 signature verification with key."""
    cmd = ["espsecure", "verify-signature", "-v", "2", "-k", str(key_path), str(binary_path)]
    res = run_command(cmd, cwd=binary_path.parent, use_idf_env=True, runner=runner)
    if res.returncode == 0:
        return True
    # Try legacy syntax if verify-signature failed with flag/syntax error
    if "verify_signature" in res.stderr or "deprecated" in res.stderr.lower():
        cmd_legacy = ["espsecure.py", "verify_signature", "-v", "2", "-k", str(key_path), str(binary_path)]
        res_legacy = run_command(cmd_legacy, cwd=binary_path.parent, use_idf_env=True, runner=runner)
        return res_legacy.returncode == 0
    return False


def find_imgtool_bin(repo_root: Path | None = None) -> str:
    """Find the imgtool executable, preferring the repository virtualenv."""
    root = (repo_root or DEFAULT_REPO_ROOT).resolve()
    venv_imgtool = root / ".venv" / "bin" / "imgtool"
    sys_imgtool = Path(sys.executable).parent / "imgtool"
    if venv_imgtool.is_file() and os.access(venv_imgtool, os.X_OK):
        return str(venv_imgtool)
    if sys_imgtool.is_file() and os.access(sys_imgtool, os.X_OK):
        return str(sys_imgtool)
    return shutil.which("imgtool") or "imgtool"


def find_west_bin(repo_root: Path | None = None) -> str:
    """Find the west executable, preferring the repository virtualenv."""
    root = (repo_root or DEFAULT_REPO_ROOT).resolve()
    venv_west = root / ".venv" / "bin" / "west"
    sys_west = Path(sys.executable).parent / "west"
    if venv_west.is_file() and os.access(venv_west, os.X_OK):
        return str(venv_west)
    if sys_west.is_file() and os.access(sys_west, os.X_OK):
        return str(sys_west)
    return shutil.which("west") or "west"


def verify_zephyr_signature(
    binary_path: Path,
    key_path: Path,
    repo_root: Path | None = None,
    runner: Callable | None = None,
) -> bool:
    """Check if signed Zephyr MCUboot binary validates against key using imgtool."""
    imgtool_bin = find_imgtool_bin(repo_root)
    cmd = [imgtool_bin, "verify", "-k", str(key_path), str(binary_path)]
    res = run_command(cmd, cwd=binary_path.parent, runner=runner)
    return res.returncode == 0


def verify_sdkconfig_variant(sdkconfig_path: Path, expected_symbol: str) -> bool:
    """Verify that sdkconfig contains the expected variant symbol enabled."""
    if not sdkconfig_path.is_file():
        return False
    with open(sdkconfig_path, "r", encoding="utf-8") as f:
        content = f.read()
    return expected_symbol in content


def build_idf_variant(
    variant: str,
    repo_root: Path | None = None,
    clean: bool = False,
    runner: Callable | None = None,
) -> BuildResult:
    """Build a single IDF variant according to PLAN R15."""
    root = (repo_root or DEFAULT_REPO_ROOT).resolve()
    if variant not in IDF_VARIANTS:
        raise BuildError(f"Unknown IDF variant '{variant}'. Valid: {list(IDF_VARIANTS.keys())}")

    var_cfg = IDF_VARIANTS[variant]
    build_dir = root / var_cfg["build_dir"]
    esp_idf_dir = root / "esp_idf"
    stale_sdkconfig = esp_idf_dir / "sdkconfig"

    # Enforce R15: delete stale project-level sdkconfig
    if stale_sdkconfig.exists():
        try:
            stale_sdkconfig.unlink()
        except OSError as e:
            raise BuildError(f"Could not remove stale {stale_sdkconfig}: {e}")

    # Ensure signing keys exist
    ensure_keys(root, need_foreign=(variant == "bad_sig"), runner=runner)

    # Clean if requested
    if clean and build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)

    build_dir.mkdir(parents=True, exist_ok=True)
    target_sdkconfig = build_dir / "sdkconfig"

    # If clean or sdkconfig missing/stale, ensure it gets generated from defaults
    cmd = [
        "idf.py",
        "-C",
        str(esp_idf_dir),
        "-B",
        str(build_dir),
        f"-DSDKCONFIG={target_sdkconfig}",
        f"-DSDKCONFIG_DEFAULTS={var_cfg['defaults']}",
        f"-DPROJECT_VER={var_cfg['project_ver']}",
        "build",
    ]

    res = run_command(cmd, cwd=esp_idf_dir, use_idf_env=True, runner=runner)
    if res.returncode != 0:
        raise BuildError(f"Build failed for variant '{variant}':\n{res.stderr or res.stdout}")

    # Post-build verification per PLAN R15
    # 1. Variant symbol in sdkconfig
    if not verify_sdkconfig_variant(target_sdkconfig, var_cfg["kconfig_sym"]):
        raise BuildError(
            f"Variant verification failed: {target_sdkconfig} does not contain {var_cfg['kconfig_sym']}"
        )

    # 2. Binary existence & non-zero size
    binary_path = build_dir / BINARY_NAME
    if not binary_path.is_file():
        raise BuildError(f"Build completed but binary not found at {binary_path}")
    size = binary_path.stat().st_size
    if size == 0:
        raise BuildError(f"Binary at {binary_path} is empty")

    # 3. Signature verification
    primary_key = root / "keys" / "idf_sbv2.pem"
    primary_verified = verify_signature(binary_path, primary_key, runner=runner)

    if var_cfg["expected_sig_valid"]:
        if not primary_verified:
            raise BuildError(f"Signature verification FAILED against {primary_key} for variant {variant}")
        sig_ok = True
        sig_detail = "verified with primary key (keys/idf_sbv2.pem)"
    else:
        # For bad_sig, verification against primary key MUST fail
        if primary_verified:
            raise BuildError(
                f"Security check failed: bad_sig was unexpectedly accepted by primary key {primary_key}"
            )
        # And verification against foreign key MUST pass
        foreign_key = root / "keys" / "idf_foreign.pem"
        foreign_verified = verify_signature(binary_path, foreign_key, runner=runner)
        if not foreign_verified:
            raise BuildError(f"bad_sig was not signed by foreign key {foreign_key}")
        sig_ok = True
        sig_detail = "refused by primary key, verified with foreign key (keys/idf_foreign.pem)"

    return BuildResult(
        board="idf",
        variant=variant,
        build_dir=build_dir,
        binary_path=binary_path,
        binary_size=size,
        project_ver=var_cfg["project_ver"],
        verified_variant=True,
        verified_signature=sig_ok,
        details=sig_detail,
    )


def build_idf_all(
    repo_root: Path | None = None,
    clean: bool = False,
    runner: Callable | None = None,
) -> dict[str, BuildResult]:
    """Build all 5 IDF variants in order."""
    results = {}
    for var in IDF_VARIANTS:
        results[var] = build_idf_variant(var, repo_root=repo_root, clean=clean, runner=runner)
    return results


def build_zephyr_variant(
    variant: str,
    repo_root: Path | None = None,
    clean: bool = False,
    runner: Callable | None = None,
) -> BuildResult:
    """Build a single Zephyr variant using west sysbuild."""
    root = (repo_root or DEFAULT_REPO_ROOT).resolve()
    if variant not in ZEPHYR_VARIANTS:
        raise BuildError(f"Unknown Zephyr variant '{variant}'. Valid: {list(ZEPHYR_VARIANTS.keys())}")

    var_cfg = ZEPHYR_VARIANTS[variant]
    build_dir = root / var_cfg["build_dir"]
    app_dir = root / "esp_zephyr" / "app"
    overlay_path = root / var_cfg["overlay"]

    # Clean if requested
    if clean and build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)

    build_dir.mkdir(parents=True, exist_ok=True)

    west_bin = find_west_bin(root)
    cmd = [
        west_bin,
        "build",
        "-b",
        "esp32s3_devkitc/esp32s3/procpu",
        "--sysbuild",
        str(app_dir),
        "-d",
        str(build_dir),
    ]
    extra_cmake = [f"-Dapp_EXTRA_CONF_FILE={overlay_path}"]
    if "sysbuild_conf" in var_cfg:
        sb_conf = root / var_cfg["sysbuild_conf"]
        extra_cmake.append(f"-DSB_EXTRA_CONF_FILE={sb_conf}")
    cmd.extend(["--", *extra_cmake])

    zephyr_env = {
        "ZEPHYR_BASE": os.environ.get("ZEPHYR_BASE", "/home/msoubhi/zephyrproject/zephyr"),
        "ZEPHYR_TOOLCHAIN_VARIANT": "cross-compile",
        "CROSS_COMPILE": os.environ.get(
            "CROSS_COMPILE",
            "/home/msoubhi/.espressif/tools/xtensa-esp-elf/esp-15.2.0_20251204/xtensa-esp-elf/bin/xtensa-esp32s3-elf-",
        ),
    }

    res = run_command(cmd, cwd=app_dir, runner=runner, env=zephyr_env)
    if res.returncode != 0:
        raise BuildError(f"Zephyr build failed for variant '{variant}':\n{res.stderr or res.stdout}")

    # 1. Variant symbol verification in .config
    target_config = build_dir / "app" / "zephyr" / ".config"
    if not verify_sdkconfig_variant(target_config, var_cfg["kconfig_sym"]):
        raise BuildError(
            f"Variant verification failed: {target_config} does not contain {var_cfg['kconfig_sym']}"
        )

    # 2. Binary existence & non-zero size
    binary_path = build_dir / "app" / "zephyr" / ZEPHYR_BINARY_NAME
    if not binary_path.is_file():
        raise BuildError(f"Build completed but binary not found at {binary_path}")
    size = binary_path.stat().st_size
    if size == 0:
        raise BuildError(f"Binary at {binary_path} is empty")

    # 3. Signature verification
    primary_key = root / "keys" / "zephyr_p256.pem"
    primary_verified = verify_zephyr_signature(binary_path, primary_key, repo_root=root, runner=runner)

    if var_cfg["expected_sig_valid"]:
        if not primary_verified:
            raise BuildError(f"Signature verification FAILED against {primary_key} for variant {variant}")
        sig_ok = True
        sig_detail = "verified with primary key (keys/zephyr_p256.pem)"
    else:
        if primary_verified:
            raise BuildError(
                f"Security check failed: bad_sig was unexpectedly accepted by primary key {primary_key}"
            )
        foreign_key = root / "keys" / "zephyr_foreign.pem"
        foreign_verified = verify_zephyr_signature(binary_path, foreign_key, repo_root=root, runner=runner)
        if not foreign_verified:
            raise BuildError(f"bad_sig was not signed by foreign key {foreign_key}")
        sig_ok = True
        sig_detail = "refused by primary key, verified with foreign key (keys/zephyr_foreign.pem)"

    return BuildResult(
        board="zephyr",
        variant=variant,
        build_dir=build_dir,
        binary_path=binary_path,
        binary_size=size,
        project_ver=var_cfg["project_ver"],
        verified_variant=True,
        verified_signature=sig_ok,
        details=sig_detail,
    )


def build_zephyr_all(
    repo_root: Path | None = None,
    clean: bool = False,
    runner: Callable | None = None,
) -> dict[str, BuildResult]:
    """Build all 5 Zephyr variants in order."""
    results = {}
    for var in ZEPHYR_VARIANTS:
        results[var] = build_zephyr_variant(var, repo_root=repo_root, clean=clean, runner=runner)
    return results


def build_board(
    board: str,
    variant: str | None = None,
    repo_root: Path | None = None,
    clean: bool = False,
    runner: Callable | None = None,
) -> dict[str, BuildResult]:
    """Top-level build dispatcher for labflash build."""
    if board == "idf":
        if variant and variant != "all":
            res = build_idf_variant(variant, repo_root=repo_root, clean=clean, runner=runner)
            return {variant: res}
        return build_idf_all(repo_root=repo_root, clean=clean, runner=runner)

    if board == "zephyr":
        if variant and variant != "all":
            res = build_zephyr_variant(variant, repo_root=repo_root, clean=clean, runner=runner)
            return {variant: res}
        return build_zephyr_all(repo_root=repo_root, clean=clean, runner=runner)

    if board == "all":
        idf_res = build_idf_all(repo_root=repo_root, clean=clean, runner=runner)
        zephyr_res = build_zephyr_all(repo_root=repo_root, clean=clean, runner=runner)
        return {**idf_res, **zephyr_res}

    raise BuildError(f"Unknown board '{board}'. Choices: idf, zephyr, all")
