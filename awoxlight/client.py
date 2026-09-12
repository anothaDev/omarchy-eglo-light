"""Async bleak client for a single AwoX/Eglo Telink-mesh light (or mesh gateway)."""
from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass
from os import urandom
from typing import Callable, Optional

from bleak import BleakClient

from . import packet as pkt

log = logging.getLogger(__name__)

MESH_DEFAULT_NAME = "unpaired"
MESH_DEFAULT_PASSWORD = "1234"

PAIR_CHAR = "00010203-0405-0607-0809-0a0b0c0d1914"
COMMAND_CHAR = "00010203-0405-0607-0809-0a0b0c0d1912"
STATUS_CHAR = "00010203-0405-0607-0809-0a0b0c0d1911"

# Command opcodes
C_POWER = 0xD0
C_LIGHT_MODE = 0x33
C_PRESET = 0xC8
C_WHITE_TEMPERATURE = 0xF0
C_WHITE_BRIGHTNESS = 0xF1
C_COLOR = 0xE2
C_COLOR_BRIGHTNESS = 0xF2
C_SEQ_COLOR_DURATION = 0xF5
C_SEQ_FADE_DURATION = 0xF6
C_MESH_ADDRESS = 0xE0
C_MESH_RESET = 0xE3
C_MESH_GROUP = 0xD7


class AuthError(Exception):
    pass


@dataclass
class LightState:
    mesh_id: int
    mode: int
    on: bool
    white_brightness: int  # 1..0x7f
    white_temp: int  # 0..0x7f (0 = cold, 0x7f = warm)
    color_brightness: int  # 0xa..0x64
    red: int
    green: int
    blue: int
    product_id: int = 0

    @property
    def is_color_mode(self) -> bool:
        return self.mode in (3, 7)


class AwoxLight:
    def __init__(self, mac: str, mesh_name: str = MESH_DEFAULT_NAME, mesh_password: str = MESH_DEFAULT_PASSWORD, adapter: str | None = None):
        self.mac = mac.upper()
        self.mesh_name = mesh_name.encode()
        self.mesh_password = mesh_password.encode()
        if len(self.mesh_name) > 16 or len(self.mesh_password) > 16:
            raise ValueError("mesh credentials too long")
        self._client = BleakClient(self.mac, adapter=adapter) if adapter else BleakClient(self.mac)
        self.session_key: Optional[bytes] = None
        self.mesh_id = 0
        self.state: Optional[LightState] = None
        self.on_state: Optional[Callable[[LightState], None]] = None
        self.use_notify = False  # Eglo firmware drops the link on CCCD write; poll instead

    # -- connection -------------------------------------------------------
    async def connect(self, timeout: float = 20.0) -> None:
        await self._client.connect(timeout=timeout)
        # From here on the transport is up: any failure must drop it, or BlueZ
        # keeps the link open with nobody holding it and the lamp stays frozen.
        try:
            session_random = urandom(8)
            await self._client.write_gatt_char(PAIR_CHAR, pkt.make_pair_packet(self.mesh_name, self.mesh_password, session_random), response=True)
            await self._client.write_gatt_char(STATUS_CHAR, b"\x01", response=True)
            reply = bytes(await self._client.read_gatt_char(PAIR_CHAR))
            if reply[:1] == b"\x0d":
                if len(reply) < 9:
                    raise RuntimeError("short pair reply")
                self.session_key = pkt.make_session_key(self.mesh_name, self.mesh_password, session_random, reply[1:9])
            elif reply[:1] == b"\x0e":
                raise AuthError("mesh name/password rejected")
            else:
                raise RuntimeError(f"unexpected pair reply {reply.hex()}")
            if self.use_notify:
                try:
                    await self._client.start_notify(STATUS_CHAR, self._on_notify)
                except Exception as e:  # noqa: BLE001 - Eglo firmware rejects CCCD write and drops link
                    log.debug("start_notify unsupported (%s); polling read_status instead", e)
        except BaseException:
            await self.disconnect()
            raise
        log.info("connected to %s (mesh %s)", self.mac, self.mesh_name.decode())

    async def disconnect(self) -> None:
        self.session_key = None
        try:
            await self._client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    @property
    def connected(self) -> bool:
        return self.session_key is not None and self._client.is_connected

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.disconnect()

    # -- status -------------------------------------------------------------
    def _on_notify(self, _handle, data: bytearray) -> None:
        if not self.session_key:
            return
        msg = pkt.decrypt_packet(self.session_key, self.mac, bytes(data))
        if msg is None:
            log.debug("notify: checksum mismatch %s", bytes(data).hex())
            return
        self._parse_status(msg)

    def _parse_status(self, msg: bytes) -> None:
        log.debug("status raw %s", msg.hex())
        mesh_id = msg[3]
        mode = msg[12]
        if mode >= 40:
            return
        wb, wt = struct.unpack("BB", msg[13:15])
        cb, r, g, b = struct.unpack("BBBB", msg[15:19])
        self.state = LightState(mesh_id, mode, bool(mode % 2), wb, wt, cb, r, g, b)
        if self.on_state:
            self.on_state(self.state)

    async def read_status(self) -> Optional[LightState]:
        assert self.session_key
        raw = bytes(await self._client.read_gatt_char(STATUS_CHAR))
        msg = pkt.decrypt_packet(self.session_key, self.mac, raw)
        if msg:
            self._parse_status(msg)
        return self.state

    # -- commands -----------------------------------------------------------
    async def write_command(self, command: int, data: bytes, dest: int | None = None) -> None:
        assert self.session_key, "not connected"
        dest = self.mesh_id if dest is None else dest
        packet = pkt.make_command_packet(self.session_key, self.mac, dest, command, data)
        log.debug("cmd 0x%02x data %s -> %d", command, data.hex(), dest)
        await self._client.write_gatt_char(COMMAND_CHAR, packet, response=False)

    async def on(self, dest=None):
        await self.write_command(C_POWER, b"\x01", dest)

    async def off(self, dest=None):
        await self.write_command(C_POWER, b"\x00", dest)

    async def set_color(self, r: int, g: int, b: int, dest=None):
        await self.write_command(C_COLOR, struct.pack("BBBB", 0x04, r, g, b), dest)

    async def set_color_brightness(self, level: int, dest=None):
        """level 0x0a..0x64 (10..100 %)."""
        await self.write_command(C_COLOR_BRIGHTNESS, struct.pack("B", max(0x0A, min(0x64, level))), dest)

    async def set_white(self, temp: int, brightness: int, dest=None):
        """temp 0..0x7f (0 cold, 0x7f warm), brightness 1..0x7f."""
        await self.write_command(C_WHITE_TEMPERATURE, struct.pack("B", max(0, min(0x7F, temp))), dest)
        await self.write_command(C_WHITE_BRIGHTNESS, struct.pack("B", max(1, min(0x7F, brightness))), dest)

    async def set_white_brightness(self, brightness: int, dest=None):
        await self.write_command(C_WHITE_BRIGHTNESS, struct.pack("B", max(1, min(0x7F, brightness))), dest)

    async def set_white_temperature(self, temp: int, dest=None):
        await self.write_command(C_WHITE_TEMPERATURE, struct.pack("B", max(0, min(0x7F, temp))), dest)

    async def set_preset(self, num: int, dest=None):
        await self.write_command(C_PRESET, struct.pack("B", num), dest)

    async def set_sequence_durations(self, color_ms: int, fade_ms: int, dest=None):
        await self.write_command(C_SEQ_COLOR_DURATION, struct.pack("<I", color_ms), dest)
        await self.write_command(C_SEQ_FADE_DURATION, struct.pack("<I", fade_ms), dest)

    # -- mesh administration --------------------------------------------------
    async def set_mesh(self, name: str, password: str, long_term_key: str) -> bool:
        """Re-key the light into a new mesh. Light blinks on success."""
        if not self.session_key:
            raise ValueError("not connected")
        if len(name.encode()) > 16 or len(password.encode()) > 16:
            raise ValueError("mesh credentials too long")
        for opcode, value in ((0x04, name), (0x05, password), (0x06, long_term_key)):
            enc = pkt.encrypt(self.session_key, value.encode())
            await self._client.write_gatt_char(PAIR_CHAR, bytes([opcode]) + bytes(enc), response=True)
        await asyncio.sleep(1)
        reply = bytes(await self._client.read_gatt_char(PAIR_CHAR))
        ok = reply[0] == 0x07
        if ok:
            self.mesh_name, self.mesh_password = name.encode(), password.encode()
        return ok

    async def set_mesh_id(self, mesh_id: int):
        await self.write_command(C_MESH_ADDRESS, struct.pack("<H", mesh_id))
        self.mesh_id = mesh_id

    async def reset_mesh(self):
        await self.write_command(C_MESH_RESET, b"\x00")


MANUFACTURER_ID = 0x0160  # AwoX / Telink mesh state beacon


def parse_advertisement(manufacturer_data: dict[int, bytes]) -> Optional[LightState]:
    """Decode the state beacon Eglo/AwoX lights put in their BLE advertisements.

    Layout (observed on Eglo Connect, fw 2.x):
      [0]    product id (see devices.py)   [1] ?   [2:6] MAC tail reversed   [6:10] vendor bytes
      [10]   ?               [11]  mode (bit0 = on, 0/1 white, 2/3 colour)
      [12]   brightness (white 1..0x7f / colour 0x0a..0x64)
      [13]   white temp (white) / red (colour)   [14] green  [15] blue
    """
    data = manufacturer_data.get(MANUFACTURER_ID)
    if not data or len(data) < 16:
        return None
    mode = data[11]
    on = bool(mode & 1)
    product = data[0]
    if mode in (2, 3, 6, 7):
        return LightState(0, mode, on, 0, 0, data[12], data[13], data[14], data[15], product)
    return LightState(0, mode, on, data[12], data[13], 0, 0, 0, 0, product)
