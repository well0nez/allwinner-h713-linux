#!/usr/bin/env python3
"""Build a synthetic TSE file for the h713-pq tests.

No vendor byte is copied: the grammar is written out from AP3f 1.2 (header,
group, module, state, attribute records), AP3p 1.5 (the gamma payload) and
AP3r 1.1 (the UI_ColorTemp selectors), the curves are invented here. The three
channels end on three different values on purpose -- that is where a board's
white balance lives (AP3r 1.4).

Usage:  python3 make_tse_fixture.py <file> [project-id]
"""

import struct
import sys
import zlib

GAMMA_PLUGIN = 0x00090009
UI_COLOR_TEMP = 0x3003
#: The vendor's own state order: warm, cool, normal (AP3r 1.1).
STATE_TEMPS = (0x30030001, 0x30030000, 0x30030002)
#: Per state and channel: end point and exponent of the invented curve.
CURVES = (
    ((4000, 1.35), (3800, 1.40), (3600, 1.50)),      # "warm"
    ((3400, 1.50), (3700, 1.42), (4090, 1.30)),      # "cool"
    ((3900, 1.38), (4090, 1.36), (4020, 1.34)),      # "normal"
)


def curve(end, exponent):
    """1024 monotone samples of 12 bit, ending exactly on ``end``."""
    return [int(round(end * pow(x / 1023.0, exponent))) for x in range(1024)]


def gamma_state_blob(banks):
    """Three banks of 1024 samples -> 512 records of 9 bytes (AP3p 1.5)."""
    out = bytearray()
    for i in range(512):
        low = [banks[c][2 * i] for c in range(3)]
        high = [banks[c][2 * i + 1] for c in range(3)]
        out += bytes(low[c] & 0xFF for c in range(3))
        out += bytes(high[c] & 0xFF for c in range(3))
        out += bytes(((high[c] >> 4) & 0xF0) | ((low[c] >> 8) & 0x0F)
                     for c in range(3))
    return bytes(out)


def _name(text):
    raw = text.encode("ascii") + b"\0"
    return bytes([len(raw)]) + raw


def _attrs(pairs):
    """TFDAttrProp::Load: u16 tag 4, 2 header bytes, u32 count, records."""
    out = struct.pack("<HHI", 4, 1, len(pairs))
    for tag, values in pairs:
        out += struct.pack("<HI", tag, len(values))
        out += b"".join(struct.pack("<I", v) for v in values)
    return out


def gamma_module(project, states):
    """One TTFDGammaFW module with its states and its payload."""
    body = struct.pack("<HHIIB", 13, 1, len(states), 0x00049002, 2)
    body += _name("Gamma_0x%04x" % project)
    body += struct.pack("<I", len(states))
    for index in range(len(states)):
        body += struct.pack("<HHHH", 8, 1, 0x2000 + 0x1000 * index, 0x4900)
        body += _attrs([(5, [0x00050000]), (UI_COLOR_TEMP, [STATE_TEMPS[index]])])
    payload = struct.pack("<I", len(states))
    for blob in states:
        payload += struct.pack("<I", len(blob)) + blob
    body += struct.pack("<II", GAMMA_PLUGIN, 1)
    body += struct.pack("<II", 0x20000009, len(payload)) + payload
    body += _attrs([])
    return body


def build(path, project=0x0030):
    banks = [[curve(end, exponent) for end, exponent in state]
             for state in CURVES]
    module = gamma_module(project, [gamma_state_blob(b) for b in banks])
    group = struct.pack("<HHIIBHH", 17, 1, 1, 0x49, 2, project, 0)
    group += _name("ProjectID_0x%04x" % project)
    group += struct.pack("<I", 1) + module
    body = struct.pack("<I", 1) + group
    header = (b"TSE" + bytes([2]) + struct.pack("<HIIHHII", 26, 0x1891B001,
              0x66F64E84, project, 0, 26 + len(body), zlib.crc32(body)))
    with open(str(path), "wb") as f:
        f.write(header + body)
    return banks


if __name__ == "__main__":
    build(sys.argv[1], int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x0030)
    print(sys.argv[1])


# --------------------------------------------------------------------------
# pq_custom.TSE: the picture parameters (AP3f 1.3 to 1.5)
# --------------------------------------------------------------------------
FEATURE_PLUGIN = 0x0009101F
#: name -> (segments as (x0, x1, y0, y1), registers as (address, width, mask)).
#: The saturation curve carries the vendor's own slope of 1.28, so the device
#: measurement of 07.09. (SetSaturation 60 -> 0x4C) is reproducible from it.
FEATURES = (
    ("mp_saturation_1", ((0, 50, 0, 64), (50, 75, 64, 96), (75, 100, 96, 128)),
     ((0x05140508, 32, 0x00FF0000),)),
    ("mp_tint_1", ((0, 50, 256, 0), (50, 100, 0, -256)),
     ((0x05140508, 32, 0x000003FF),)),
    ("mp_brightness", ((0, 50, 923, 0), (50, 100, 0, 100)),
     ((0x051405BC, 32, 0x0003FF00),)),
)


def _be(value):
    return bytes(reversed(struct.pack("<f", float(value))))


def custom_module():
    blob = struct.pack("<H", len(FEATURES))
    for index, (label, _seg, _reg) in enumerate(FEATURES):
        blob += label.encode("ascii") + b"\0" + struct.pack("<I", 0x00EE0000 + index)
    for index, (_label, segments, regs) in enumerate(FEATURES):
        body = struct.pack("<H", len(segments))
        for point in segments:
            body += b"".join(_be(v) for v in point)
        body += struct.pack("<H", len(regs))
        for address, width, mask in regs:
            body += struct.pack("<BIBIB", 0, address, width, mask, 0)
        blob += struct.pack("<IIBH", 0x00EE0000 + index, 11 + len(body), 0, 1) + body
    payload = struct.pack("<HI", 0, 6 + len(blob)) + blob
    body = struct.pack("<HHIIB", 13, 1, 1, 0x00049003, 0)
    body += _name("UI_Feature") + struct.pack("<I", 1)
    body += struct.pack("<HHHH", 8, 1, 0x3000, 0x4900) + _attrs([])
    body += struct.pack("<II", FEATURE_PLUGIN, 1)
    body += struct.pack("<II", 0x20000009, len(payload)) + payload + _attrs([])
    return body


def build_custom(path):
    """A synthetic pq_custom.TSE with the group UI_Feature."""
    group = struct.pack("<HHIIBHH", 17, 1, 1, 0x4A, 3, 0, 0)
    group += _name("UI_Feature") + struct.pack("<I", 1) + custom_module()
    body = struct.pack("<I", 1) + group
    header = (b"TSE" + bytes([5]) + struct.pack("<HIIHHII", 26, 0x18816066,
              0x66C6D8FC, 0, 0, 26 + len(body), zlib.crc32(body)))
    with open(str(path), "wb") as f:
        f.write(header + body)
    return FEATURES
