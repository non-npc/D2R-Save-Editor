from __future__ import annotations

class BitStream:
    """Bit-level access over a bytearray using **LSB-first** bit order within each byte."""

    def __init__(self, buf: bytearray, bit_offset: int = 0):
        self.buf = buf
        self.bitpos = bit_offset

    def tell(self) -> int:
        return self.bitpos

    def seek(self, bitpos: int) -> None:
        self.bitpos = int(bitpos)

    def read_bits(self, n: int) -> int:
        v = self.get_bits(self.bitpos, n)
        self.bitpos += n
        return v

    def get_bits(self, bitpos: int, n: int) -> int:
        if n <= 0:
            return 0
        out = 0
        for i in range(n):
            p = bitpos + i
            byte_i = p // 8
            bit_i = p % 8
            if byte_i >= len(self.buf):
                raise ValueError("Bit read out of range")
            bit = (self.buf[byte_i] >> bit_i) & 1
            out |= (bit << i)
        return out

    def set_bits(self, bitpos: int, n: int, value: int) -> None:
        if n <= 0:
            return
        for i in range(n):
            p = bitpos + i
            byte_i = p // 8
            bit_i = p % 8
            if byte_i >= len(self.buf):
                raise ValueError("Bit write out of range")
            bit = (value >> i) & 1
            if bit:
                self.buf[byte_i] |= (1 << bit_i)
            else:
                self.buf[byte_i] &= ~(1 << bit_i)
