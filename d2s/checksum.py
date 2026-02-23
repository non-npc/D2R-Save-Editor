from __future__ import annotations

def _rol32(x: int, r: int) -> int:
    x &= 0xFFFFFFFF
    r &= 31
    return ((x << r) | (x >> (32 - r))) & 0xFFFFFFFF

def calculate_checksum(data: bytes) -> int:
    """
    Checksum per krisives/d2s-format:
    - bytes 0x0C..0x0F treated as zero
    - sum = rol(sum, 1) + byte
    """
    s = 0
    for i, b in enumerate(data):
        if 0x0C <= i < 0x10:
            b = 0
        s = (_rol32(s, 1) + b) & 0xFFFFFFFF
    return s

def write_checksum(buf: bytearray) -> int:
    chk = calculate_checksum(bytes(buf))
    # little-endian uint32 at 0x0C
    buf[0x0C:0x10] = chk.to_bytes(4, "little", signed=False)
    return chk
