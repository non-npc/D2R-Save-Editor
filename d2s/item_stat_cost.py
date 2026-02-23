"""
ItemStatCost data for parsing D2 item property lists.
Used to skip past advanced item extended data.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

# stat_id -> (encode, save_bits, save_param_bits, save_add)
# encode 4 = unused, save_bits 0 or 1024 = invalid
_STATS: Dict[int, Tuple[int, int, int, int]] = {}
_LOADED = False

ITEMSTAT_END_ID = 0x1FF


def _load_item_stat_cost() -> None:
    global _LOADED, _STATS
    if _LOADED:
        return
    _LOADED = True
    path = Path(__file__).parent / "data" / "ItemStatCost.txt"
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.strip().split("\n")
        if not lines:
            return
        header = lines[0].replace("\r", "").split("\t")
        if len(header) < 20:
            header = lines[0].replace("\r", "").split()
        col_idx = {h: i for i, h in enumerate(header)}
        idx_id = col_idx.get("ID", 1)
        idx_encode = col_idx.get("Encode", 15)
        idx_save_bits = col_idx.get("Save Bits", 22)
        idx_save_add = col_idx.get("Save Add", 23)
        idx_save_param = col_idx.get("Save Param Bits", 24)
        delim = "\t" if "\t" in lines[0] else None
        for line in lines[1:]:
            line = line.replace("\r", "")
            parts = line.split("\t") if delim else line.split()
            if len(parts) <= max(idx_id, idx_encode, idx_save_bits, idx_save_add, idx_save_param):
                continue
            try:
                stat_id = int(parts[idx_id])
                encode = int(parts[idx_encode]) if parts[idx_encode] else 1
                save_bits = int(parts[idx_save_bits]) if parts[idx_save_bits] else 0
                save_add = int(parts[idx_save_add]) if parts[idx_save_add] else 0
                save_param = int(parts[idx_save_param]) if parts[idx_save_param] else 0
            except (ValueError, IndexError):
                continue
            if encode == 4 or save_bits == 0 or save_bits >= 1024:
                continue
            _STATS[stat_id] = (encode, save_bits, save_add, save_param)
    except Exception:
        pass


def get_stat_bits(stat_id: int) -> int:
    """Return total bits to read for this stat in a property list. 0 if invalid."""
    _load_item_stat_cost()
    if stat_id not in _STATS:
        return 9 if 0 <= stat_id < 512 else 0
    encode, save_bits, save_add, save_param = _STATS[stat_id]
    if encode == 2:
        return 6 + 10 + save_bits
    if encode == 3:
        return 6 + 10 + 8 + 8
    if save_param > 0:
        return save_param + save_bits
    return save_bits


def skip_property_list(bs, bit_start: int, max_bit: int = 0) -> int:
    """
    Skip a D2 item property list starting at bit_start.
    Returns the bit position after the list.
    Uses LSB-first BitStream with get_bits(bitpos, n).
    If max_bit > 0, stops if pos would exceed it to avoid reading past buffer.
    """
    pos = bit_start
    while True:
        if max_bit > 0 and pos + 9 > max_bit:
            return pos
        stat_id = bs.get_bits(pos, 9)
        pos += 9
        if stat_id == ITEMSTAT_END_ID:
            break
        if stat_id > ITEMSTAT_END_ID:
            return pos
        n = get_stat_bits(stat_id)
        if n <= 0:
            return pos
        if max_bit > 0 and pos + n > max_bit:
            return pos
        pos += n
    return pos
