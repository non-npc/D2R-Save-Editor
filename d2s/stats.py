from __future__ import annotations
from typing import Optional, Dict
from .models import Stats, StatEntry
from .bitstream import BitStream

STATS_MARKER = b"gf"
TERMINATOR = 0x1FF

# From nokka/d2s docs (attributes section). citeturn1view0
ATTR_NAMES = {
    0: "Strength",
    1: "Energy",
    2: "Dexterity",
    3: "Vitality",
    4: "Unused stats",
    5: "Unused skills",
    6: "Current HP",
    7: "Max HP",
    8: "Current Mana",
    9: "Max Mana",
    10: "Current Stamina",
    11: "Max Stamina",
    12: "Level",
    13: "Experience",
    14: "Gold",
    15: "Stashed Gold",
}

ATTR_BITS = {
    0: 10,
    1: 10,
    2: 10,
    3: 10,
    4: 10,
    5: 8,
    6: 21,
    7: 21,
    8: 21,
    9: 21,
    10: 21,
    11: 21,
    12: 7,
    13: 32,
    14: 25,
    15: 25,
}

def find_stats(raw: bytes) -> Optional[Stats]:
    idx = raw.find(STATS_MARKER)
    if idx == -1:
        return None
    # bitstream starts immediately after 'gf'
    bs = BitStream(bytearray(raw), (idx + 2) * 8)
    entries: Dict[int, StatEntry] = {}

    while True:
        id_bitpos = bs.tell()
        stat_id = bs.read_bits(9)
        if stat_id == TERMINATOR:
            end_bitpos = bs.tell()
            break
        bit_len = ATTR_BITS.get(stat_id)
        if bit_len is None:
            # Unknown stat id encountered; bail safely without modifying.
            return None
        value_bitpos = bs.tell()
        value = bs.read_bits(bit_len)
        entries[stat_id] = StatEntry(
            stat_id=stat_id,
            name=ATTR_NAMES.get(stat_id, f"Stat {stat_id}"),
            bit_length=bit_len,
            value=value,
            id_bitpos=id_bitpos,
            value_bitpos=value_bitpos,
        )

    return Stats(offset=idx, entries=entries, end_bitpos=end_bitpos)

def set_stat(raw: bytearray, stats: Stats, stat_id: int, value: int) -> None:
    if stat_id not in stats.entries:
        raise ValueError("Stat not present in this save file.")
    ent = stats.entries[stat_id]
    # Clamp to bit length
    maxv = (1 << ent.bit_length) - 1
    if value < 0 or value > maxv:
        raise ValueError(f"Value out of range for {ent.name} (0..{maxv}).")
    bs = BitStream(raw)
    bs.set_bits(ent.value_bitpos, ent.bit_length, int(value))
    ent.value = int(value)
