"""Telink mesh packet crypto (AES-ECB based CCM-like scheme, byte-reversed)."""
from __future__ import annotations

import struct
from os import urandom

from Crypto.Cipher import AES


def encrypt(key: bytes, value: bytes) -> bytearray:
    assert len(key) == 16
    k = bytearray(key)
    val = bytearray(value.ljust(16, b"\x00"))
    k.reverse()
    val.reverse()
    out = bytearray(AES.new(bytes(k), AES.MODE_ECB).encrypt(bytes(val)))
    out.reverse()
    return out


def make_checksum(key: bytes, nonce: bytes, payload: bytes) -> bytearray:
    base = (nonce + bytes([len(payload)])).ljust(16, b"\x00")
    check = encrypt(key, base)
    for i in range(0, len(payload), 16):
        chunk = bytearray(payload[i : i + 16].ljust(16, b"\x00"))
        check = bytearray(a ^ b for a, b in zip(check, chunk))
        check = encrypt(key, check)
    return check


def crypt_payload(key: bytes, nonce: bytes, payload: bytes) -> bytearray:
    """Symmetric: used for both encryption and decryption."""
    base = bytearray((b"\x00" + nonce).ljust(16, b"\x00"))
    result = bytearray()
    for i in range(0, len(payload), 16):
        enc = encrypt(key, bytes(base))
        result += bytearray(a ^ b for a, b in zip(enc, payload[i : i + 16]))
        base[0] += 1
    return result


def _mac_reversed(mac: str) -> bytearray:
    a = bytearray.fromhex(mac.replace(":", ""))
    a.reverse()
    return a


def make_command_packet(key: bytes, mac: str, dest_id: int, command: int, data: bytes) -> bytes:
    seq = urandom(3)
    nonce = bytes(_mac_reversed(mac)[0:4]) + b"\x01" + seq
    payload = (struct.pack("<H", dest_id) + struct.pack("B", command) + b"\x60\x01" + data).ljust(15, b"\x00")
    check = make_checksum(key, nonce, payload)
    payload = crypt_payload(key, nonce, payload)
    return seq + bytes(check[0:2]) + bytes(payload)


def decrypt_packet(key: bytes, mac: str, packet: bytes) -> bytes | None:
    nonce = bytes(_mac_reversed(mac)[0:3]) + bytes(packet[0:5])
    payload = crypt_payload(key, nonce, packet[7:])
    check = make_checksum(key, nonce, payload)
    if bytes(check[0:2]) != bytes(packet[5:7]):
        return None
    return bytes(packet[0:7]) + bytes(payload)


def _name_pass(mesh_name: bytes, mesh_password: bytes) -> bytearray:
    n = bytearray(mesh_name.ljust(16, b"\x00"))
    p = bytearray(mesh_password.ljust(16, b"\x00"))
    return bytearray(a ^ b for a, b in zip(n, p))


def make_pair_packet(mesh_name: bytes, mesh_password: bytes, session_random: bytes) -> bytes:
    enc = encrypt(session_random.ljust(16, b"\x00"), bytes(_name_pass(mesh_name, mesh_password)))
    return b"\x0c" + session_random + bytes(enc[0:8])


def make_session_key(mesh_name: bytes, mesh_password: bytes, session_random: bytes, response_random: bytes) -> bytes:
    return bytes(encrypt(bytes(_name_pass(mesh_name, mesh_password)), session_random + response_random))
