"""labflash provision — write WiFi credentials & bearer token to NVS (BL-024).

Implements the host provisioning workflow per PLAN §5.2 and §7.2:
- Generates an NVS partition binary image containing namespace 'lab',
  with keys 'ssid', 'psk', and 'token'.
- Flashes the image to the 'nvs' partition at offset 0x9000 (size 0x6000).
- Guarantees zero credentials in source or stdout/logs (AC2).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

NVS_PARTITION_OFFSET = 0x9000
NVS_PARTITION_SIZE = 0x6000  # 24 KB = 24576 bytes


def generate_nvs_csv(ssid: str, psk: str, token: str) -> str:
    """Generate the CSV representation for the NVS partition generator."""
    return (
        "key,type,encoding,value\n"
        "lab,namespace,,\n"
        f"ssid,data,string,{ssid}\n"
        f"psk,data,string,{psk}\n"
        f"token,data,string,{token}\n"
    )


def load_credentials_from_env(path: str | Path) -> dict[str, str]:
    """Parse a credentials.env file without external dependencies."""
    out: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Credentials file not found: {path}")

    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "WIFI_SSID":
                    out["ssid"] = v
                elif k == "WIFI_PSK":
                    out["psk"] = v
                elif k == "OTA_TOKEN":
                    out["token"] = v

    return out


def generate_nvs_bin(ssid: str, psk: str, token: str, out_bin: Path) -> None:
    """Generate binary NVS image using esp_idf_nvs_partition_gen or IDF script."""
    csv_content = generate_nvs_csv(ssid, psk, token)
    out_bin = Path(out_bin).resolve()

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "nvs.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        # 1. Try python -m esp_idf_nvs_partition_gen.nvs_partition_gen
        cmd = [
            sys.executable,
            "-m",
            "esp_idf_nvs_partition_gen.nvs_partition_gen",
            "generate",
            str(csv_file),
            str(out_bin),
            hex(NVS_PARTITION_SIZE),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and out_bin.exists():
            return

        # 2. Try ESP-IDF's components script if IDF_PATH is set or at ~/tools/esp-idf
        idf_path = os.environ.get("IDF_PATH", str(Path.home() / "tools" / "esp-idf"))
        idf_gen_py = Path(idf_path) / "components" / "nvs_flash" / "nvs_partition_generator" / "nvs_partition_gen.py"
        if idf_gen_py.exists():
            cmd2 = [
                sys.executable,
                str(idf_gen_py),
                "generate",
                str(csv_file),
                str(out_bin),
                hex(NVS_PARTITION_SIZE),
            ]
            res2 = subprocess.run(cmd2, capture_output=True, text=True, check=False)
            if res2.returncode == 0 and out_bin.exists():
                return

        raise RuntimeError(
            f"Failed to generate NVS partition image: {res.stderr or res2.stderr if 'res2' in locals() else res.stderr}"
        )


def provision_idf(port: str, ssid: str, psk: str, token: str) -> None:
    """Write WiFi credentials and bearer token to NVS on the IDF board over USB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        nvs_bin = Path(tmpdir) / "nvs.bin"
        generate_nvs_bin(ssid, psk, token, nvs_bin)

        # Flash to offset 0x9000
        esptool_bin = shutil.which("esptool") or shutil.which("esptool.py") or f"{sys.executable} -m esptool"
        if isinstance(esptool_bin, str) and " " in esptool_bin:
            cmd = esptool_bin.split()
        else:
            cmd = [esptool_bin]

        cmd.extend([
            "--chip", "esp32s3",
            "-p", port,
            "-b", "460800",
            "write-flash",
            hex(NVS_PARTITION_OFFSET),
            str(nvs_bin),
        ])

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            # Check if write_flash (with underscore) is needed
            cmd[cmd.index("write-flash")] = "write_flash"
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if res.returncode != 0:
            raise RuntimeError(f"esptool failed to flash NVS partition: {res.stderr}")
