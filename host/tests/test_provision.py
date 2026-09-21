"""Unit tests for labflash provision (BL-024)."""
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from labflash.provision import (
    NVS_PARTITION_OFFSET,
    NVS_PARTITION_SIZE,
    generate_nvs_bin,
    generate_nvs_csv,
    load_credentials_from_env,
    provision_idf,
)


def test_generate_nvs_csv():
    csv_text = generate_nvs_csv(ssid="TestWiFi", psk="SecretPass123", token="token-abc")
    lines = [line.strip() for line in csv_text.strip().splitlines()]
    assert "key,type,encoding,value" in lines[0]
    assert "lab,namespace,," in lines[1]
    assert "ssid,data,string,TestWiFi" in lines[2]
    assert "psk,data,string,SecretPass123" in lines[3]
    assert "token,data,string,token-abc" in lines[4]


def test_load_credentials_from_env():
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write('# Comment line\n')
        f.write('WIFI_SSID="MySSID"\n')
        f.write("WIFI_PSK='SecretPassword'\n")
        f.write('OTA_TOKEN=token123\n')
        f.flush()
        temp_path = f.name

    try:
        creds = load_credentials_from_env(temp_path)
        assert creds["ssid"] == "MySSID"
        assert creds["psk"] == "SecretPassword"
        assert creds["token"] == "token123"
    finally:
        os.unlink(temp_path)


def test_generate_nvs_bin():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_bin = Path(tmpdir) / "nvs.bin"
        generate_nvs_bin("TestSSID", "TestPSK", "TestToken", out_bin)
        assert out_bin.exists()
        assert out_bin.stat().st_size == NVS_PARTITION_SIZE


@patch("labflash.provision.generate_nvs_bin")
@patch("subprocess.run")
def test_provision_idf(mock_run, mock_gen):
    mock_run.return_value = MagicMock(returncode=0)
    provision_idf(
        port="/dev/ttyACM0",
        ssid="TestSSID",
        psk="TestPSK",
        token="TestToken",
    )
    assert mock_gen.called
    assert mock_run.called
    cmd = mock_run.call_args[0][0]
    assert "--chip" in cmd
    assert "esp32s3" in cmd
    assert "write_flash" in cmd or "write-flash" in cmd
    assert hex(NVS_PARTITION_OFFSET) in cmd or str(NVS_PARTITION_OFFSET) in cmd or "0x9000" in cmd
