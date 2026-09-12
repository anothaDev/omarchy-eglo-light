"""AwoX / Eglo mesh product ids and what each device can do.

The first byte of a device's state beacon (manufacturer data, company id
0x0160) is its product id. The table below is derived from the device list
maintained by the EspHome-AwoX-BLE-mesh-hub project
(https://github.com/fsaris/EspHome-AwoX-BLE-mesh-hub), MIT licensed.

Kinds:  rgb  = colour + tunable white     tw  = tunable white only
        dim  = single white, dimmable      plug = on/off socket
"""
from __future__ import annotations

from typing import TypedDict

KINDS = ("rgb", "tw", "dim", "plug")

# product_id: (kind, manufacturer, name, model)
DEVICES: dict[int, tuple[str, str, str, str]] = {
    0x13: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 9', 'SMLm_C9'),
    0x14: ('tw', 'AwoX', 'SmartLIGHT White Mesh 13W', 'SMLm_W13'),
    0x15: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 13W', 'SMLm_C13'),
    0x16: ('tw', 'AwoX', 'SmartLIGHT White Mesh 15W', 'SMLm_W15'),
    0x17: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 15W', 'SMLm_C15'),
    0x21: ('tw', 'AwoX', 'SmartLIGHT White Mesh 9W', 'SSMLm_w9'),
    0x22: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 9W', 'SSMLm_c9'),
    0x23: ('rgb', 'EGLO', 'EGLOBulb A60 9W', 'ESMLm_c9'),
    0x24: ('rgb', 'KERIA', 'Keria SmartLIGHT Color Mesh 9W', 'KSMLm_c9'),
    0x25: ('rgb', 'EGLO', 'EGLOPanel 30X30', 'EPanel_300'),
    0x26: ('rgb', 'EGLO', 'EGLOPanel 60X60', 'EPanel_600'),
    0x27: ('rgb', 'EGLO', 'EGLO Ceiling DOWNLIGHT', 'EMod_Ceil'),
    0x29: ('rgb', 'EGLO', 'EGLOBulb G95 13W', 'ESMLm_c13g'),
    0x2A: ('rgb', 'KERIA', 'Keria SmartLIGHT Color Mesh 13W Globe', 'KSMLm_c13g'),
    0x2B: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 13W Globe', 'SMLm_c13g'),
    0x30: ('rgb', 'EGLO', 'EGLOPanel 30X120', 'EPanel_120'),
    0x32: ('rgb', 'EGLO', 'Spot 120', 'EGLOSpot 120/w'),
    0x33: ('rgb', 'EGLO', 'Spot 170', 'EGLOSpot 170/w'),
    0x34: ('rgb', 'EGLO', 'Spot 225', 'EGLOSpot 225/w'),
    0x35: ('rgb', 'EGLO', 'Giron-C 17W', 'EGLO 32589'),
    0x36: ('rgb', 'EGLO', 'EGLO Ceiling GIRON 30', 'ECeil_g38'),
    0x37: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 5W GU10', 'SMLm_c5_GU10'),
    0x38: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 5W E14', 'SMLm_c5_E14'),
    0x3A: ('rgb', 'KERIA', 'Keria SmartLIGHT Color Mesh 5W GU10', 'KSMLm_c5_GU10'),
    0x3B: ('rgb', 'KERIA', 'Keria SmartLIGHT Color Mesh 5W E14', 'KSMLm_c5_E14'),
    0x3C: ('rgb', 'EGLO', 'SmartLIGHT Color Mesh 5W GU10', 'ESMLm_c5_GU10'),
    0x3D: ('rgb', 'EGLO', 'SmartLIGHT Color Mesh 5W E14', 'ESMLm_c5_E14'),
    0x3F: ('rgb', 'EGLO', 'EGLO Surface round', 'EFueva_225r'),
    0x40: ('rgb', 'EGLO', 'EGLO Surface square', 'EFueva_225s'),
    0x41: ('rgb', 'EGLO', 'EGLO Surface round', 'EFueva_300r'),
    0x42: ('rgb', 'EGLO', 'EGLO Surface square', 'EFueva_300s'),
    0x43: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 9W', 'SMLm_c9s'),
    0x44: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 13W', 'SMLm_c13gs'),
    0x45: ('rgb', 'EGLO', 'EGLOBulb A60 9W', 'ESMLm_c9s'),
    0x46: ('rgb', 'EGLO', 'EGLOBulb G95 13W', 'ESMLm_c13gs'),
    0x47: ('rgb', 'KERIA', 'Keria SmartLIGHT Color Mesh 9W', 'KSMLm_c9s'),
    0x48: ('rgb', 'KERIA', 'Keria SmartLIGHT Color Mesh 13W Glob', 'KSMLm_c13gs'),
    0x49: ('dim', 'EGLO', 'EGLOBulb A60 Warm', 'ESMLm_w9w'),
    0x4A: ('dim', 'EGLO', 'EGLOBulb A60 Neutral', 'ESMLm_w9n'),
    0x4B: ('rgb', 'EGLO', 'EGLO Ceiling', 'ECeiling_30'),
    0x4C: ('rgb', 'EGLO', 'EGLO Pendant', 'EPendant_30'),
    0x4D: ('rgb', 'EGLO', 'EGLO Pendant', 'EPendant_20'),
    0x4E: ('rgb', 'EGLO', 'EGLO Stripled 3m', 'EStrip_3m'),
    0x4F: ('rgb', 'EGLO', 'EGLO Stripled 5m', 'EStrip_5m'),
    0x50: ('dim', 'EGLO', 'Outdoor', 'EOutdoor_w14w'),
    0x51: ('rgb', 'EGLO', 'EGLOSpot', 'ETriSpot_85'),
    0x53: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 9W', 'SMLm_c9i'),
    0x54: ('rgb', 'EGLO', 'EGLOBulb A60 9W', 'ESMLm_c9i'),
    0x55: ('rgb', 'KERIA', 'Keria SmartLIGHT Color Mesh 9W', 'KSMLm_c9i'),
    0x56: ('rgb', 'EGLO', 'EGLOPanel 62X62', 'EPanel_620'),
    0x57: ('rgb', 'EGLO', 'EGLOPanel 45X45', 'EPanel_450'),
    0x59: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 13W Globe', 'SMLm_c13gi'),
    0x5A: ('rgb', 'EGLO', 'EGLOBulb G95 13W', 'ESMLm_c13gi'),
    0x5B: ('rgb', 'KERIA', 'Keria SmartLIGHT Color Mesh 13W Globe', 'KSMLm_c13gi'),
    0x5C: ('rgb', 'AwoX', 'SmartLIGHT Color Mesh 9W', 'SSMLm_c9i'),
    0x62: ('plug', 'EGLO', 'EGLO PLUG', 'ESMP-Bm10-FR'),
    0x63: ('plug', 'EGLO', 'EGLO PLUG', 'ESMP-Bm10-GE'),
    0x64: ('tw', 'AwoX', 'SmartLIGHT White Mesh 9W', 'SMLm_w9'),
    0x65: ('tw', 'EGLO', 'SmartLIGHT White Mesh 9W', 'ESMLm_w9'),
    0x67: ('plug', 'EGLO', 'EGLO PLUG PLUS', 'SMPWBm10FR'),
    0x68: ('plug', 'EGLO', 'EGLO PLUG PLUS', 'SMPWBm10GE'),
    0x69: ('rgb', 'EGLO', 'Ceiling GIRON 60', 'ECeil_g60'),
    0x6A: ('tw', 'AwoX', 'SmartLIGHT Bulb A60 Warm', 'SMLm_w9w'),
    0x6F: ('tw', 'EGLO', 'EGLOBulb Filament G80', 'ESMLFm-w6-G80'),
    0x71: ('tw', 'EGLO', 'EGLOBulb Filament ST64', 'ESMLFm-w6-ST64'),
    0x75: ('tw', 'EGLO', 'EGLOBulb Filament G95', 'ESMLFm-w6-G95'),
    0x77: ('rgb', 'EGLO', 'EGLO Spot', 'ESpot_c5'),
    0x78: ('rgb', 'EGLO', 'EGLO Fraioli', 'EFraioli_c17'),
    0x79: ('rgb', 'EGLO', 'EGLO Frattina', 'EFrattina_c18'),
    0x7A: ('rgb', 'EGLO', 'EGLO Frattina', 'EFrattina_c27'),
    0x7B: ('rgb', 'EGLO', 'EGLOPanel 30 Round', 'EPanel_r300'),
    0x7C: ('rgb', 'EGLO', 'EGLOPanel 45 Round', 'EPanel_r450'),
    0x7D: ('rgb', 'EGLO', 'EGLOPanel 60 Round', 'EPanel_r600'),
    0x7E: ('rgb', 'EGLO', 'EGLOPanel 10X120', 'EPanel_120_10'),
    0x80: ('tw', 'EGLO', 'EPanel white round', 'EPanel_w_round'),
    0x81: ('tw', 'EGLO', 'EPanel white square', 'EPanel_w_square'),
    0x82: ('tw', 'EGLO', 'EPanel white rectangle', 'EPanel_w_rect'),
    0x83: ('tw', 'EGLO', 'ECeiling white round', 'ECeiling-w'),
    0x84: ('plug', 'EGLO', 'EGLO PLUG PLUS', 'SMPWBm10FRa'),
    0x85: ('plug', 'EGLO', 'EGLO PLUG PLUS', 'SMPWBm10GEa'),
    0x87: ('tw', 'EGLO', 'EGLO Tunable White', 'EDoubleWhite'),
    0x88: ('rgb', 'EGLO', 'EGLO Ceiling GIRON 80', 'ECeil_g80'),
    0x89: ('tw', 'EGLO', 'Outdoor Marchesa-C', 'EMarchesa_C'),
    0x8A: ('tw', 'EGLO', 'Outdoor Francari-C', 'EFrancari_C'),
    0x8B: ('plug', 'EGLO', 'EGLO PLUG', 'ESMP-Bm10-AUS'),
    0x8C: ('plug', 'EGLO', 'EGLO PLUG', 'ESMP-Bm10-UK'),
    0x8D: ('plug', 'EGLO', 'EGLO PLUG', 'ESMP-Bm10-CH'),
    0x8F: ('plug', 'EGLO', 'EGLO PLUG PLUS', 'SMPWBm10UK'),
    0x90: ('plug', 'EGLO', 'EGLO PLUG PLUS', 'SMPWBm10CH'),
    0x92: ('rgb', 'EGLO', 'EPanel square', 'EPanel_36W_square'),
    0x94: ('dim', 'EGLO', 'EGLOBulb Filament ST64', 'ESMLFm-w6w-ST64'),
    0x95: ('dim', 'EGLO', 'EGLOBulb Filament G95', 'ESMLFm-w6w-G95'),
    0x96: ('rgb', 'EGLO', 'EGLO RGB+TW', 'EGLO-RGB-TW'),
    0x97: ('tw', 'EGLO', 'EGLO Tunable White', 'EGLO-TW'),
    0x99: ('rgb', 'EGLO', 'EGLO RGB+TW', 'EGLO-RGB-TW'),
    0x9A: ('tw', 'EGLO', 'EGLO Tunable White', 'JBT_Gen_CCT_1'),
    0x9B: ('dim', 'EGLO', 'EGLO Tunable White', 'JBT_Gen_Dim_1'),
    0x9C: ('plug', 'EGLO', 'EGLO PLUG PLUS', 'SMPWBm10FRb'),
    0x9D: ('plug', 'EGLO', 'EGLO PLUG PLUS', 'SMPWBm10GEb'),
    0x9E: ('plug', 'EGLO', 'EGLO PLUG PLUS', 'SMPWBm10AUSb'),
    0x9F: ('plug', 'EGLO', 'EGLO PLUG PLUS', 'SMPWBm10UKb'),
    0xA0: ('plug', 'EGLO', 'EGLO PLUG PLUS', 'SMPWBm10CHb'),
    0xA1: ('rgb', 'EGLO', 'EGLOLed Relax', 'ELedRelax'),
    0xA2: ('rgb', 'EGLO', 'EGLOLed Stripe', 'ELedStripe'),
    0xA3: ('rgb', 'EGLO', 'EGLOLed Plus', 'ELedPlus'),
    0xA4: ('tw', 'EGLO', 'EGLOLed Plus TW', 'ELedPlus-TW'),
    0xA5: ('dim', 'EGLO', 'EGLOLed Plus Dimmable', 'ELedPlus-Dimm'),
    0xA6: ('tw', 'EGLO', 'EGLOBulb', 'ESMLFm-w6-TW'),
    0xA7: ('dim', 'EGLO', 'EGLOBulb', 'ESMLFm-w6-Dimm'),
    0xA8: ('rgb', 'EGLO', 'ECeiling square', 'ECeiling-24W-square'),
    0xA9: ('rgb', 'EGLO', 'EGLO RGB+TW', 'EGLO-RGB-TW-IPSU'),
    0xAA: ('tw', 'EGLO', 'EGLO Tunable White', 'EGLO-TW-IPSU'),
    0xAC: ('rgb', 'EGLO', 'EGLO frameless', 'EPanel-Frameless'),
    0xAD: ('tw', 'EGLO', 'EGLO Tunable White', 'EDoubleWhite-ipsu'),
}


class DeviceInfo(TypedDict):
    product_id: int
    known: bool
    kind: str
    manufacturer: str
    name: str
    model: str
    color: bool
    temperature: bool
    brightness: bool


def device_info(product_id: int) -> DeviceInfo:
    """Capabilities for a product id. Unknown ids are treated as full RGB
    lamps so no control is hidden from a lamp that might support it."""
    entry = DEVICES.get(product_id)
    if entry:
        kind, manufacturer, name, model = entry
    else:
        kind, manufacturer, name, model = "rgb", "AwoX", "Unknown device", f"0x{product_id:02X}"
    return {
        "product_id": product_id,
        "known": entry is not None,
        "kind": kind,
        "manufacturer": manufacturer,
        "name": name,
        "model": model,
        "color": kind == "rgb",
        "temperature": kind in ("rgb", "tw"),
        "brightness": kind != "plug",
    }
