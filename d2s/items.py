from __future__ import annotations
from typing import Optional, List
import struct
from .models import Items, ItemSimpleHeader
from .bitstream import BitStream
from . import item_stat_cost
from . import item_names

ITEMS_MARKER = b"JM"

# Rarity: 0=inferior, 1=normal, 2=superior, 3=magic, 4=rare, 5=set, 6=unique
RARITY_MAGIC, RARITY_RARE, RARITY_SET, RARITY_UNIQUE = 3, 4, 5, 6


def _skip_advanced_item(bs: BitStream, start_bit: int, type_code: str, runeword: bool, socketed: bool, personalized: bool, max_bit: int) -> int:
    """Skip past advanced item extended data. Returns bit position after item."""
    pos = start_bit + 111
    if pos + 43 > max_bit:
        return pos
    # id (32), level (7), rarity (4)
    item_id = bs.get_bits(pos, 32)
    pos += 32
    level = bs.get_bits(pos, 7)
    pos += 7
    rarity = bs.get_bits(pos, 4)
    pos += 4

    # multiplePictures
    if pos + 1 > max_bit:
        return pos
    if bs.get_bits(pos, 1):
        pos += 4
    else:
        pos += 1
    # classSpecific
    if pos + 1 > max_bit:
        return pos
    if bs.get_bits(pos, 1):
        pos += 12
    else:
        pos += 1

    # rarity-specific
    if rarity == RARITY_MAGIC:
        pos += 7
    elif rarity == RARITY_RARE:
        pos += 7 + 7 + 7
    elif rarity == RARITY_SET:
        pos += 27
    elif rarity == RARITY_UNIQUE:
        pos += 27

    # runeword id
    if runeword:
        pos += 16

    # personalized name (max 50 chars to avoid infinite loop on corrupt data)
    if personalized:
        for _ in range(50):
            if pos + 7 > max_bit:
                break
            c = bs.get_bits(pos, 7)
            pos += 7
            if c == 0:
                break

    # tome (tbk, tsc)
    code_lower = type_code.strip().lower()[:3]
    if code_lower in ("tbk", "tsc"):
        pos += 5

    # timestamp
    pos += 1

    # armor defense
    if item_names.is_armor(type_code):
        pos += 11

    # durability (armor or weapon)
    if item_names.is_armor(type_code) or item_names.is_weapon(type_code):
        if pos + 8 <= max_bit:
            max_dur = bs.get_bits(pos, 8)
            pos += 8
            if max_dur > 0:
                pos += 9

    # quantity (stackable)
    if item_names.is_stackable(type_code):
        pos += 9

    # sockets
    if socketed:
        pos += 4

    # set bonuses bits (read before advancing)
    set_bonus_bits_val = 0
    if rarity == RARITY_SET and pos + 5 <= max_bit:
        set_bonus_bits_val = bs.get_bits(pos, 5)
        pos += 5

    # property list
    pos = item_stat_cost.skip_property_list(bs, pos, max_bit)

    # set bonus property lists (one per set bit)
    if rarity == RARITY_SET:
        for _ in range(5):
            if set_bonus_bits_val & 1:
                pos = item_stat_cost.skip_property_list(bs, pos, max_bit)
            set_bonus_bits_val >>= 1

    # runeword property list
    if runeword:
        pos = item_stat_cost.skip_property_list(bs, pos, max_bit)

    return pos


def find_items(raw: bytes, start_search: int = 0) -> Optional[Items]:
    idx = raw.find(ITEMS_MARKER, start_search)
    if idx == -1:
        return None
    if idx + 4 > len(raw):
        return None
    count = struct.unpack_from("<H", raw, idx+2)[0]

    bit_start = (idx + 4) * 8
    bs = BitStream(bytearray(raw), bit_start)
    parsed: List[ItemSimpleHeader] = []
    stopped_on_advanced = False
    max_bit = len(raw) * 8

    for _ in range(count):
        start_bit = bs.tell()
        if start_bit + 112 > max_bit:
            stopped_on_advanced = True
            break

        def gb(off, n):
            return bs.get_bits(start_bit + off, n)

        identified = bool(gb(20, 1))
        socketed = bool(gb(27, 1))
        ear = bool(gb(32, 1))
        starter = bool(gb(33, 1))
        simple_flag = bool(gb(37, 1))  # bit 37 = "item is simple" per D2 format docs
        ethereal = bool(gb(38, 1))
        personalized = bool(gb(40, 1))
        runeword = bool(gb(42, 1))
        parent = gb(58, 3)
        equipped = gb(61, 4)
        column = gb(65, 4)
        row = gb(69, 3)
        stash = gb(73, 3)

        # Item code: bits 76-107 (32 bits = 4 chars), e.g. "amu " -> "amu"
        type_bits = gb(76, 32)
        type_bytes = int(type_bits).to_bytes(4, "little", signed=False)
        try:
            type_code = type_bytes.decode("ascii", errors="replace").rstrip(" \x00")[:3]
        except Exception:
            type_code = "???"

        compact = simple_flag  # alias for model compatibility
        if simple_flag:
            end_bit = start_bit + 112
        else:
            try:
                end_bit = _skip_advanced_item(bs, start_bit, type_code, runeword, socketed, personalized, max_bit)
            except ValueError:
                stopped_on_advanced = True
                break

        item = ItemSimpleHeader(
            start_bit=start_bit,
            end_bit=end_bit,
            identified=identified,
            socketed=socketed,
            ear=ear,
            starter_gear=starter,
            compact=compact,
            ethereal=ethereal,
            personalized=personalized,
            runeword=runeword,
            parent=parent,
            equipped=equipped,
            column=column,
            row=row,
            stash=stash,
            type_code=type_code,
            advanced=(not simple_flag),
        )
        parsed.append(item)
        bs.seek(end_bit)

    return Items(offset=idx, count=count, parsed=parsed, stopped_on_advanced=stopped_on_advanced)

def set_simple_item_flag_bits(raw: bytearray, item: ItemSimpleHeader, *, identified=None, ethereal=None, socketed=None) -> None:
    bs = BitStream(raw)
    if identified is not None:
        bs.set_bits(item.start_bit + 20, 1, 1 if identified else 0)
        item.identified = bool(identified)
    if socketed is not None:
        bs.set_bits(item.start_bit + 27, 1, 1 if socketed else 0)
        item.socketed = bool(socketed)
    if ethereal is not None:
        bs.set_bits(item.start_bit + 38, 1, 1 if ethereal else 0)
        item.ethereal = bool(ethereal)
