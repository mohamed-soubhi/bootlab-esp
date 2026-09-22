"""BL-027: wire-protocol tests for the ble_ota client (no BLE hardware needed).

The expected byte layouts come from the component source
(espressif/ble_ota 0.1.18, src/nimble_ota.c), not from memory:
  START  = 01 00 <fw_len u32 LE>            (20-byte command frame, CRC16 at 18..19 LE)
  data   = <sector u16 LE> <packet seq u8> <payload>; last packet of a sector uses
           seq 0xFF and payload = data + 2-byte sector CRC16
  ACK    = 20 bytes: <sector LE16> <status 0=ok 2=retry> 00 <expected sector LE16> .. crc
"""
import pytest
from labflash import idf_ble_ota as ota

SECTOR = ota.SECTOR_SIZE


def test_crc16_ccitt_matches_the_devices_check_value():
    # CRC-16/XMODEM (init 0, poly 0x1021), the variant nimble_ota.c implements.
    assert ota.crc16_ccitt(b"123456789") == 0x31C3


def test_uuids_are_the_ones_in_nimble_ota_c():
    assert ota.SERVICE_UUID.startswith("00008018")
    assert ota.RECV_FW_UUID.startswith("00008020")
    assert ota.COMMAND_UUID.startswith("00008022")


def test_start_command_layout_and_crc():
    frame = ota.start_command(1052672)
    assert len(frame) == ota.CMD_FRAME_LEN == 20
    assert frame[0:2] == b"\x01\x00"
    assert int.from_bytes(frame[2:6], "little") == 1052672
    assert frame[6:18] == bytes(12)
    assert int.from_bytes(frame[18:20], "little") == ota.crc16_ccitt(frame[:18])


def test_stop_command_layout():
    frame = ota.stop_command()
    assert frame[0:2] == b"\x02\x00" and len(frame) == 20
    assert int.from_bytes(frame[18:20], "little") == ota.crc16_ccitt(frame[:18])


def _ack(sector, status, expected=0, cmd=None):
    body = bytearray(20)
    body[0:2] = sector.to_bytes(2, "little")
    body[2] = status
    body[4:6] = expected.to_bytes(2, "little")
    if cmd is not None:
        body[0:2] = cmd.to_bytes(2, "little")
    body[18:20] = ota.crc16_ccitt(bytes(body[:18])).to_bytes(2, "little")
    return bytes(body)


def test_parse_sector_ack_ok_and_retry():
    ok = ota.parse_ack(_ack(7, 0))
    assert (ok.sector, ok.status, ok.crc_ok) == (7, 0, True) and ok.is_success
    retry = ota.parse_ack(_ack(7, 2, expected=5))
    assert retry.status == 2 and retry.expected_sector == 5 and not retry.is_success


def test_parse_ack_rejects_bad_crc_and_short_frames():
    bad = bytearray(_ack(1, 0))
    bad[10] ^= 0xFF
    assert ota.parse_ack(bytes(bad)).crc_ok is False
    with pytest.raises(ValueError):
        ota.parse_ack(b"\x00" * 5)


def test_parse_command_ack_start():
    # device answers START with 03 00 01 00 ...
    body = bytes([3, 0, 1, 0]) + bytes(14)
    ack = ota.parse_ack(body + ota.crc16_ccitt(body).to_bytes(2, "little"))
    assert ack.crc_ok and ack.is_command_ack_for(ota.CMD_START)


@pytest.mark.parametrize("mtu", [23, 100, 185, 247, 512])
def test_sector_packets_reassemble_and_respect_the_mtu(mtu):
    data = bytes((i * 7 + 3) % 256 for i in range(SECTOR))
    packets = ota.sector_packets(5, data, mtu)
    payload_max = mtu - ota.ATT_HEADER - ota.PKT_HEADER
    assert all(len(p) <= mtu - ota.ATT_HEADER for p in packets)
    assert all(p[0:2] == (5).to_bytes(2, "little") for p in packets)
    # regular packets count 0,1,2..; only the last one is 0xFF
    assert [p[2] for p in packets[:-1]] == list(range(len(packets) - 1))
    assert packets[-1][2] == 0xFF
    body = b"".join(p[3:] for p in packets)
    assert body[:-2] == data                       # nothing lost, nothing added
    assert int.from_bytes(body[-2:], "little") == ota.crc16_ccitt(data)
    assert len(packets[-1]) - ota.PKT_HEADER >= 2  # room for the CRC (device needs >= 2)
    assert max(len(p) - ota.PKT_HEADER for p in packets) <= payload_max


def test_sector_packets_rejects_an_unusably_small_mtu():
    with pytest.raises(ValueError):
        ota.sector_packets(0, bytes(SECTOR), 8)


def test_split_sectors_requires_4k_alignment_and_indexes_them():
    image = bytes(range(256)) * 16 * 3          # 3 x 4096
    sectors = ota.split_sectors(image)
    assert [i for i, _ in sectors] == [0, 1, 2]
    assert all(len(s) == SECTOR for _, s in sectors)
    with pytest.raises(ValueError):
        ota.split_sectors(image + b"\x00")       # not aligned: the last-sector quirk is unsupported


def test_1mb_image_matches_the_real_signed_image_size():
    assert len(ota.split_sectors(bytes(1052672))) == 257


def test_mac_prefix():
    assert ota._mac_prefix("E0:72:A1:AA:23:90") == "e0:72:a1:aa:23"
    assert ota._mac_prefix("E0-72-A1-AA-23-90") == "e0:72:a1:aa:23"


def test_find_device_success():
    import asyncio
    from unittest.mock import MagicMock, patch
    dev = MagicMock(name="dev", address="E0:72:A1:AA:23:92")
    dev.name = ota.DEFAULT_NAME
    adv = MagicMock(service_uuids=[ota.SERVICE_UUID], local_name=ota.DEFAULT_NAME)

    with patch("bleak.BleakScanner.discover", return_value={"k": (dev, adv)}):
        found = asyncio.run(ota.find_device(board_mac="E0:72:A1:AA:23:90"))
        assert found == dev


def test_find_device_not_found():
    import asyncio
    from unittest.mock import patch
    with patch("bleak.BleakScanner.discover", return_value={}), \
         pytest.raises(ota.BleOtaError, match="expected exactly one BLE OTA device, found 0"):
        asyncio.run(ota.find_device(board_mac="E0:72:A1:AA:23:90"))


def test_upload_mocked():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    start_ack = _ack(ota.CMD_ACK, ota.CMD_START)
    sector_ack = _ack(0, ota.STATUS_OK)
    stop_ack = _ack(ota.CMD_ACK, ota.CMD_STOP)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.mtu_size = 256

    callbacks = {}

    async def fake_start_notify(uuid, cb):
        callbacks[uuid] = cb

    async def fake_write_gatt_char(uuid, data, response=True):
        if uuid == ota.COMMAND_UUID:
            if data[0:2] == b"\x01\x00":  # start command
                callbacks[ota.COMMAND_UUID](None, bytearray(start_ack))
            elif data[0:2] == b"\x02\x00":  # stop command
                callbacks[ota.COMMAND_UUID](None, bytearray(stop_ack))
        elif uuid == ota.RECV_FW_UUID and data[2] == 0xFF:  # last packet of sector
            callbacks[ota.RECV_FW_UUID](None, bytearray(sector_ack))

    mock_client.start_notify = fake_start_notify
    mock_client.write_gatt_char = fake_write_gatt_char
    mock_client.disconnect = AsyncMock()

    with patch("bleak.BleakClient", return_value=mock_client):
        img = bytes(4096)  # 1 sector
        progress_calls = []
        res = asyncio.run(ota.upload(img, "E0:72:A1:AA:23:92", on_progress=lambda d, t: progress_calls.append((d, t))))
        assert res["aborted"] is False
        assert res["sectors_sent"] == 1
        assert progress_calls == [(1, 1)]

        # Test abort_after_sectors
        res_abort = asyncio.run(ota.upload(img, "E0:72:A1:AA:23:92", abort_after_sectors=1))
        assert res_abort["aborted"] is True


def test_progress_helper(capsys):
    ota._progress(1, 10)
    assert "sector 1/10" in capsys.readouterr().out


def test_cli_run_scan_only():
    import argparse
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    dev = MagicMock(name="dev", address="E0:72:A1:AA:23:92")
    dev.name = "nimble-ble-ota"

    args = argparse.Namespace(
        address=None,
        board_mac="E0:72:A1:AA:23:90",
        scan_timeout=5.0,
        scan_only=True,
    )

    with patch("labflash.idf_ble_ota.find_device", new=AsyncMock(return_value=dev)):
        rc = asyncio.run(ota._run(args))
        assert rc == 0




def test_upload_retries_when_gatt_table_incomplete_then_succeeds(monkeypatch):
    """Windows intermittently connects with an undiscovered GATT table: reconnect instead of crashing (run-2 failure)."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    monkeypatch.setattr(ota, "CONNECT_RETRY_PAUSE_S", 0)
    clients = []

    def make_client(*_a, **_k):
        c = MagicMock()
        c.__aenter__ = AsyncMock(return_value=c)
        c.__aexit__ = AsyncMock(return_value=None)
        c.services.get_characteristic = MagicMock(return_value=None if len(clients) == 0 else object())
        clients.append(c)
        return c

    # 2nd client has the characteristics -> proceeds into the transfer (start_notify on a MagicMock is not awaitable
    # -> TypeError proves we got past discovery)
    with patch("bleak.BleakClient", side_effect=make_client), pytest.raises(Exception) as ei:
        asyncio.run(ota.upload(bytes(4096), "E0:72:A1:AA:23:92"))
    assert len(clients) == 2 and "never appeared" not in str(ei.value)


def test_upload_raises_bleotaerror_when_gatt_never_appears(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    monkeypatch.setattr(ota, "CONNECT_RETRY_PAUSE_S", 0)
    made = []

    def make_client(*_a, **_k):
        c = MagicMock()
        c.__aenter__ = AsyncMock(return_value=c)
        c.__aexit__ = AsyncMock(return_value=None)
        c.services.get_characteristic = MagicMock(return_value=None)
        made.append(c)
        return c

    with patch("bleak.BleakClient", side_effect=make_client), pytest.raises(ota.BleOtaError, match="never appeared"):
        asyncio.run(ota.upload(bytes(4096), "E0:72:A1:AA:23:92"))
    assert len(made) == ota.CONNECT_ATTEMPTS
