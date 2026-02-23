from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

@dataclass
class Header:
    signature: int
    version: int
    file_size: int
    checksum: int
    active_weapon: int

    # These are discovered heuristically for newer/unknown versions
    name: str
    name_offset: int  # absolute offset where 16-byte C-string begins

    status: Optional[int] = None
    progression: Optional[int] = None
    char_class: Optional[int] = None
    level: Optional[int] = None
    class_offset: Optional[int] = None
    level_offset: Optional[int] = None

@dataclass
class Skills:
    offset: int
    values: List[int]  # 30 bytes

@dataclass
class QuestEntry:
    act: int
    index_in_act: int
    name: str
    value: int  # uint16 raw
    offset: int  # absolute offset in file to 2-byte value

@dataclass
class Quests:
    offset: int
    difficulties: Dict[str, List[QuestEntry]]  # "Normal"/"Nightmare"/"Hell"
    special_flags: Dict[Tuple[str, int], Dict[str, bool]]

@dataclass
class Waypoints:
    offset: int
    difficulties: Dict[str, int]  # bitfield int for 39 bits (LSB order)

@dataclass
class StatEntry:
    stat_id: int
    name: str
    bit_length: int
    value: int
    id_bitpos: int
    value_bitpos: int

@dataclass
class Stats:
    offset: int  # byte offset of 'gf'
    entries: Dict[int, StatEntry]
    end_bitpos: int  # bitpos after 0x1FF terminator

@dataclass
class ItemSimpleHeader:
    start_bit: int
    end_bit: int
    identified: bool
    socketed: bool
    ear: bool
    starter_gear: bool
    compact: bool
    ethereal: bool
    personalized: bool
    runeword: bool
    parent: int
    equipped: int
    column: int
    row: int
    stash: int
    type_code: str
    advanced: bool = False

@dataclass
class Items:
    offset: int
    count: int
    parsed: List[ItemSimpleHeader]
    stopped_on_advanced: bool

@dataclass
class SaveFile:
    raw: bytearray
    header: Header
    skills: Optional[Skills] = None
    quests: Optional[Quests] = None
    waypoints: Optional[Waypoints] = None
    stats: Optional[Stats] = None
    items: Optional[Items] = None
    path: Optional[str] = None
