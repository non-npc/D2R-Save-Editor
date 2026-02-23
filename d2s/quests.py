from __future__ import annotations
from typing import Optional, Dict, List, Tuple
import struct
from .models import Quests, QuestEntry

QUESTS_MARKER = b"Woo!"
DIFFS = ["Normal", "Nightmare", "Hell"]

QUEST_NAMES = {
    1: ["Den of Evil", "Sisters' Burial Grounds", "Tools of the Trade", "The Search for Cain", "The Forgotten Tower", "Sisters to the Slaughter"],
    2: ["Radament's Lair", "The Horadric Staff", "Tainted Sun", "Arcane Sanctuary", "The Summoner", "The Seven Tombs"],
    3: ["Lam Esen's Tome", "Khalim's Will", "Blade of the Old Religion", "The Golden Bird", "The Blackened Temple", "The Guardian"],
    4: ["The Fallen Angel", "Terror's End", "Hell's Forge"],
    5: ["Siege on Harrogath", "Rescue on Mount Arreat", "Prison of Ice", "Betrayal of Harrogath", "Rite of Passage", "Eve of Destruction"],
}

def _read_u16(raw: bytes, off: int) -> int:
    return struct.unpack_from("<H", raw, off)[0]

def _write_u16(raw: bytearray, off: int, v: int) -> None:
    struct.pack_into("<H", raw, off, int(v) & 0xFFFF)

def find_quests(raw: bytes) -> Optional[Quests]:
    idx = raw.find(QUESTS_MARKER)
    if idx == -1:
        return None
    start = idx + 10  # 4 + 6 unknown bytes
    if start + 96*3 > len(raw):
        return None

    difficulties: Dict[str, List[QuestEntry]] = {}
    special: Dict[Tuple[str, int], Dict[str, bool]] = {}

    for d_i, dname in enumerate(DIFFS):
        base = start + d_i * 96
        entries: List[QuestEntry] = []
        act_blocks = [
            (1, 2, 6),
            (2, 18, 6),
            (3, 34, 6),
            (4, 50, 3),
            (5, 70, 6),
        ]
        for act, qoff, qcount in act_blocks:
            for qi in range(qcount):
                off = base + qoff + qi * 2
                val = _read_u16(raw, off)
                name = QUEST_NAMES[act][qi]
                entries.append(QuestEntry(act=act, index_in_act=qi, name=name, value=val, offset=off))
                if act == 5 and qi == 2:
                    special[(dname, off)] = {"scroll_consumed": bool((val >> 7) & 1)}
        difficulties[dname] = entries

    return Quests(offset=idx, difficulties=difficulties, special_flags=special)

def set_quest_completed(raw: bytearray, entry: QuestEntry, completed: bool) -> None:
    v = _read_u16(raw, entry.offset)
    if completed:
        v |= 1
        v &= ~2
    else:
        v &= ~1
    _write_u16(raw, entry.offset, v)

def set_prison_of_ice_scroll(raw: bytearray, entry: QuestEntry, consumed: bool) -> None:
    v = _read_u16(raw, entry.offset)
    if consumed:
        v |= (1 << 7)
    else:
        v &= ~(1 << 7)
    _write_u16(raw, entry.offset, v)
