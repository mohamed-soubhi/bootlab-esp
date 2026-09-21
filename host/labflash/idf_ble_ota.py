"""labflash idf_ble_ota — client for the ESP-IDF BLE OTA service (BL-027, PLAN 7.2).

Speaks the wire protocol of espressif/ble_ota 0.1.18 (NimBLE). The layouts below were
read from the component source (src/nimble_ota.c), not from documentation:

  GATT service 0x8018; RECV_FW 0x8020 (firmware data, write-no-response + notify),
  OTA_BAR 0x8021, COMMAND 0x8022 (write + notify), CUSTOMER 0x8023.
  START = 01 00 <fw_len u32 LE> ; STOP = 02 00. Command frames are 20 bytes, CRC16
  (init 0, poly 0x1021, "XMODEM") over bytes 0..17 stored little-endian at 18..19.
  Data = <sector u16 LE> <packet seq u8> <payload>. Sectors are 4096 bytes. Regular
  packets count 0,1,2..; the LAST packet of a sector has seq 0xFF and its payload ends
  with the 2-byte sector CRC16. The device ACKs every sector (20 bytes: sector LE16,
  status 0=ok 2=retry, 0, expected sector LE16, ..., crc) as a notification on RECV_FW;
  command ACKs (03 00 <cmd> 00 ...) arrive on COMMAND.

The protocol functions are pure (tested without hardware). bleak is imported lazily so
they also run where bleak is not installed. The client needs a BLE central, so it runs
natively on Windows (WSL2 has no Bluetooth) or on the RPi4.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

SECTOR_SIZE = 4096
CMD_FRAME_LEN = 20
ATT_HEADER = 3            # ATT opcode + handle
PKT_HEADER = 3            # sector u16 + packet seq u8
LAST_PACKET_SEQ = 0xFF
MAX_REGULAR_PACKETS = 0xFF  # seq 0..254 for regular packets; 0xFF is reserved
MIN_MTU = 23
CMD_START, CMD_STOP, CMD_ACK = 1, 2, 3
STATUS_OK, STATUS_RETRY = 0, 2
DEFAULT_NAME = "nimble-ble-ota"

ACK_TIMEOUT_S = 30.0
START_TIMEOUT_S = 10.0
SECTOR_RETRIES = 3
SCAN_TIMEOUT_S = 10.0
PROGRESS_EVERY = 16


def _uuid(short: int) -> str:
    return f"0000{short:04x}-0000-1000-8000-00805f9b34fb"


SERVICE_UUID = _uuid(0x8018)
RECV_FW_UUID = _uuid(0x8020)
OTA_BAR_UUID = _uuid(0x8021)
COMMAND_UUID = _uuid(0x8022)


class BleOtaError(RuntimeError):
    """A BLE OTA failure (no device, refused, timeout, repeated sector errors)."""


def crc16_ccitt(data: bytes) -> int:
    """CRC-16/XMODEM: init 0, poly 0x1021 -- what nimble_ota.c's crc16_ccitt() computes."""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _command(cmd: int, payload: bytes = b"") -> bytes:
    body = cmd.to_bytes(2, "little") + payload
    body = body.ljust(CMD_FRAME_LEN - 2, b"\x00")
    return body + crc16_ccitt(body).to_bytes(2, "little")


def start_command(fw_len: int) -> bytes:
    return _command(CMD_START, fw_len.to_bytes(4, "little"))


def stop_command() -> bytes:
    return _command(CMD_STOP)


@dataclass(frozen=True)
class Ack:
    raw: bytes
    sector: int
    status: int
    expected_sector: int
    crc_ok: bool

    @property
    def is_success(self) -> bool:
        return self.crc_ok and self.status == STATUS_OK

    def is_command_ack_for(self, cmd: int) -> bool:
        return self.crc_ok and self.sector == CMD_ACK and self.status == cmd


def parse_ack(frame: bytes) -> Ack:
    if len(frame) < CMD_FRAME_LEN:
        raise ValueError(f"ACK frame too short: {len(frame)} bytes")
    body, crc = frame[:CMD_FRAME_LEN - 2], int.from_bytes(frame[CMD_FRAME_LEN - 2:CMD_FRAME_LEN], "little")
    return Ack(
        raw=bytes(frame[:CMD_FRAME_LEN]),
        sector=int.from_bytes(frame[0:2], "little"),
        status=frame[2],
        expected_sector=int.from_bytes(frame[4:6], "little"),
        crc_ok=crc16_ccitt(body) == crc,
    )


def split_sectors(image: bytes) -> list[tuple[int, bytes]]:
    """(index, 4096-byte sector) pairs. Only 4096-aligned images are supported: the
    device has a special case for a short last sector that is not exercised here."""
    if not image or len(image) % SECTOR_SIZE:
        raise ValueError(f"image size {len(image)} is not a multiple of {SECTOR_SIZE}")
    return [(i // SECTOR_SIZE, image[i:i + SECTOR_SIZE]) for i in range(0, len(image), SECTOR_SIZE)]


def sector_packets(sector: int, data: bytes, mtu: int) -> list[bytes]:
    """Frame one sector for RECV_FW: <sector LE16><seq><payload>, last seq 0xFF + CRC16."""
    payload_max = mtu - ATT_HEADER - PKT_HEADER
    body = data + crc16_ccitt(data).to_bytes(2, "little")
    chunks = [body[i:i + payload_max] for i in range(0, len(body), payload_max)] if payload_max > 0 else []
    if len(chunks) > MAX_REGULAR_PACKETS or not chunks:
        raise ValueError(f"MTU {mtu} is too small to frame a {len(data)}-byte sector")
    if len(chunks) > 1 and len(chunks[-1]) < 2:
        # The device treats the last 2 bytes of the 0xFF packet as the CRC: never leave it shorter.
        need = 2 - len(chunks[-1])
        chunks[-2], chunks[-1] = chunks[-2][:-need], chunks[-2][-need:] + chunks[-1]
    head = sector.to_bytes(2, "little")
    packets = [head + bytes([seq]) + chunk for seq, chunk in enumerate(chunks[:-1])]
    packets.append(head + bytes([LAST_PACKET_SEQ]) + chunks[-1])
    return packets


# ---------------------------------------------------------------- BLE client (bleak)

def _mac_prefix(mac: str) -> str:
    return mac.lower().replace("-", ":")[:14]   # first 5 octets: the BLE address is base MAC + 2


async def find_device(address: str | None = None, board_mac: str | None = None,
                      timeout: float = SCAN_TIMEOUT_S):
    """Scan for the BLE OTA service. Refuses to guess when more than one board matches."""
    from bleak import BleakScanner

    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    hits = []
    for dev, adv in found.values():
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        if SERVICE_UUID in uuids or (adv.local_name or dev.name) == DEFAULT_NAME:
            hits.append(dev)
    if address:
        hits = [d for d in hits if d.address.lower() == address.lower()]
    if board_mac:
        hits = [d for d in hits if _mac_prefix(d.address) == _mac_prefix(board_mac)]
    if len(hits) != 1:
        names = ", ".join(f"{d.name or '?'}@{d.address}" for d in hits) or "none"
        raise BleOtaError(f"expected exactly one BLE OTA device, found {len(hits)} ({names})")
    return hits[0]


async def upload(image: bytes, address: str, on_progress: Callable[[int, int], None] | None = None,
                 abort_after_sectors: int | None = None, ack_timeout: float = ACK_TIMEOUT_S) -> dict:
    """Send `image` over BLE OTA. If abort_after_sectors is set, drop the link after that many
    sectors (the interrupted-transfer test) and return without STOP."""
    from bleak import BleakClient

    sectors = split_sectors(image)
    sector_acks: asyncio.Queue[Ack] = asyncio.Queue()
    cmd_acks: asyncio.Queue[Ack] = asyncio.Queue()

    def on_sector_ack(_h, data: bytearray) -> None:
        try:
            sector_acks.put_nowait(parse_ack(bytes(data)))
        except ValueError:
            pass

    def on_cmd_ack(_h, data: bytearray) -> None:
        try:
            cmd_acks.put_nowait(parse_ack(bytes(data)))
        except ValueError:
            pass

    async def next_ack(queue: asyncio.Queue, timeout: float, what: str) -> Ack:
        try:
            return await asyncio.wait_for(queue.get(), timeout)
        except asyncio.TimeoutError as exc:
            raise BleOtaError(f"timeout waiting for {what} ({timeout:.0f} s)") from exc

    started = time.monotonic()
    async with BleakClient(address, timeout=20.0) as client:
        mtu = max(int(getattr(client, "mtu_size", MIN_MTU)), MIN_MTU)
        await client.start_notify(RECV_FW_UUID, on_sector_ack)
        await client.start_notify(COMMAND_UUID, on_cmd_ack)

        await client.write_gatt_char(COMMAND_UUID, start_command(len(image)))
        ack = await next_ack(cmd_acks, START_TIMEOUT_S, "START ack")
        if not ack.is_command_ack_for(CMD_START):
            raise BleOtaError(f"device refused START: {ack.raw.hex()}")

        for index, data in sectors:
            for attempt in range(SECTOR_RETRIES):
                for packet in sector_packets(index, data, mtu):
                    await client.write_gatt_char(RECV_FW_UUID, packet, response=False)
                ack = await next_ack(sector_acks, ack_timeout, f"sector {index} ack")
                if ack.is_success and ack.sector == index:
                    break
                if ack.crc_ok and ack.status == STATUS_RETRY:
                    continue
                raise BleOtaError(f"sector {index}: unexpected ack {ack.raw.hex()}")
            else:
                raise BleOtaError(f"sector {index}: still failing after {SECTOR_RETRIES} attempts")
            if on_progress and (index % PROGRESS_EVERY == 0 or index == len(sectors) - 1):
                on_progress(index + 1, len(sectors))
            if abort_after_sectors is not None and index + 1 >= abort_after_sectors:
                await client.disconnect()
                return {"aborted": True, "sectors_sent": index + 1, "mtu": mtu,
                        "seconds": time.monotonic() - started}

        try:   # best effort: the device reboots into the new image right after the last ACK
            await client.write_gatt_char(COMMAND_UUID, stop_command())
            await asyncio.wait_for(cmd_acks.get(), 3.0)
        except Exception:  # noqa: S110, BLE001 - a dropped link here means the board already rebooted
            pass
    return {"aborted": False, "sectors_sent": len(sectors), "mtu": mtu,
            "seconds": time.monotonic() - started}


def _progress(done: int, total: int) -> None:
    print(f"  sector {done}/{total}", flush=True)


async def _run(args: argparse.Namespace) -> int:
    device = await find_device(args.address, args.board_mac, args.scan_timeout)
    print(f"found BLE OTA device {device.name or '?'} at {device.address}", flush=True)
    if args.scan_only:
        return 0
    with open(args.image, "rb") as fh:  # noqa: ASYNC230
        image = fh.read()
    print(f"uploading {args.image} ({len(image)} bytes, {len(image) // SECTOR_SIZE} sectors)", flush=True)
    result = await upload(image, device.address, _progress, args.abort_after)
    print(f"done: {result}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ESP-IDF BLE OTA client (BL-027)")
    ap.add_argument("--image", help="signed app .bin (4096-aligned)")
    ap.add_argument("--address", help="BLE address of the device")
    ap.add_argument("--board-mac", help="board Wi-Fi/base MAC; the BLE address must share its first 5 octets")
    ap.add_argument("--scan-only", action="store_true", help="find the device and stop")
    ap.add_argument("--abort-after", type=int, default=None, help="drop the link after N sectors")
    ap.add_argument("--scan-timeout", type=float, default=SCAN_TIMEOUT_S)
    args = ap.parse_args(argv)
    if not args.scan_only and not args.image:
        ap.error("--image is required unless --scan-only")
    try:
        return asyncio.run(_run(args))
    except BleOtaError as exc:
        print(f"BLE OTA failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
