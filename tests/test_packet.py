"""Known-answer tests for the Telink mesh packet crypto.

Expected values were produced by the reference implementation
(Leiaz/python-awox-mesh-light, packetutils.py) with fixed random bytes, so
these pin the bleak port to the protocol that real lamps speak.
"""
from unittest import mock

from awoxlight import packet as pkt
from awoxlight.client import LightState, parse_advertisement

KEY = bytes(range(16))
MAC = "A4:C1:38:78:9E:EC"
NONCE = bytes.fromhex("0102030405060708")
SESSION_RANDOM = bytes.fromhex("0102030405060708")
RESPONSE_RANDOM = bytes.fromhex("1112131415161718")


def test_session_key_matches_reference():
    key = pkt.make_session_key(b"R-D9C2DB", b"1234", SESSION_RANDOM, RESPONSE_RANDOM)
    assert key.hex() == "81c2f74ad4c33dafa71b8a812038c562"


def test_pair_packet_matches_reference():
    packet = pkt.make_pair_packet(b"R-D9C2DB", b"1234", SESSION_RANDOM)
    assert packet.hex() == "0c0102030405060708485c12d131fc6a0a"


def test_checksum_and_stream_cipher_match_reference():
    assert pkt.make_checksum(KEY, NONCE, b"hello").hex() == "a31c6362258a267defe6466acf9a28b8"
    assert pkt.crypt_payload(KEY, NONCE, b"payload-16-bytes!!").hex() == "1e745e2b084fc4df4ab4bc1a50fadf9dd0e2"


def test_command_packet_matches_reference():
    with mock.patch.object(pkt, "urandom", lambda n: b"\xaa\xbb\xcc"[:n]):
        packet = pkt.make_command_packet(KEY, MAC, 0xFFFF, 0xD0, b"\x01")
    assert packet.hex() == "aabbccde1851b2589ff91656b4a514c1acd2e617"
    assert len(packet) == 20


def test_crypt_payload_is_an_involution():
    data = b"\x01" * 15
    once = pkt.crypt_payload(KEY, NONCE, data)
    assert pkt.crypt_payload(KEY, NONCE, bytes(once)) == data


def test_decrypt_rejects_bad_checksum():
    with mock.patch.object(pkt, "urandom", lambda n: b"\x00\x00\x00"[:n]):
        packet = bytearray(pkt.make_command_packet(KEY, MAC, 1, 0xD0, b"\x01"))
    packet[7] ^= 0xFF
    assert pkt.decrypt_packet(KEY, MAC, bytes(packet)) is None


def _beacon(state_bytes: bytes) -> dict[int, bytes]:
    head = bytes.fromhex("3510ec9e7838020211ec00")
    return {0x0160: head + state_bytes + bytes(11)}


def test_parse_advertisement_white_and_colour():
    white = parse_advertisement(_beacon(bytes.fromhex("017f400000")))
    assert white == LightState(0, 1, True, 0x7F, 0x40, 0, 0, 0, 0, 0x35)
    colour = parse_advertisement(_beacon(bytes.fromhex("0364ff00ff")))
    assert colour == LightState(0, 3, True, 0, 0, 0x64, 255, 0, 255, 0x35)
    off_in_colour = parse_advertisement(_beacon(bytes.fromhex("0218ff8000")))
    assert off_in_colour is not None and not off_in_colour.on and off_in_colour.color_brightness == 0x18


def test_parse_advertisement_ignores_other_vendors():
    assert parse_advertisement({0x004C: b"\x02\x15" + bytes(20)}) is None
    assert parse_advertisement({0x0160: b"\x00" * 8}) is None


def test_device_table():
    from awoxlight.devices import DEVICES, KINDS, device_info

    giron = device_info(0x35)
    assert giron["known"] and giron["kind"] == "rgb" and giron["model"] == "EGLO 32589"
    assert giron["color"] and giron["temperature"] and giron["brightness"]
    tw = device_info(0x65)
    assert tw["kind"] == "tw" and not tw["color"] and tw["temperature"]
    plug = device_info(0x62)
    assert plug["kind"] == "plug" and not plug["brightness"]
    unknown = device_info(0xEE)
    assert not unknown["known"] and unknown["color"]  # nothing hidden for unknown lamps
    assert all(v[0] in KINDS for v in DEVICES.values())
