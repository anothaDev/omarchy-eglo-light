"""Control AwoX / Eglo Connect (Telink BLE mesh) lights over Bluetooth LE.

Protocol details derived from Leiaz/python-awox-mesh-light; this is an asyncio
port on top of bleak so it runs on modern BlueZ without bluepy.
"""
from .client import AwoxLight, LightState, MESH_DEFAULT_NAME, MESH_DEFAULT_PASSWORD, parse_advertisement

__all__ = ["AwoxLight", "LightState", "MESH_DEFAULT_NAME", "MESH_DEFAULT_PASSWORD", "parse_advertisement"]
