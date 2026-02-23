from __future__ import annotations
from typing import Optional, Dict
import struct
from .models import Waypoints

WAYPOINT_MARKER = b"WS"
DIFFS = ["Normal", "Nightmare", "Hell"]

WAYPOINTS = [
    "Rogue Encampment", "Cold Plains", "Stony Field", "Dark Wood", "Black Marsh", "Outer Cloister", "Jail Level 1", "Inner Cloister", "Catacombs Level 2",
    "Lut Gholein", "Sewers Level 2", "Dry Hills", "Halls of the Dead Level 2", "Far Oasis", "Lost City", "Palace Cellar Level 1", "Arcane Sanctuary", "Canyon of the Magi",
    "Kurast Docks", "Spider Forest", "Great Marsh", "Flayer Jungle", "Lower Kurast", "Kurast Bazaar", "Upper Kurast", "Travincal", "Durance of Hate Level 2",
    "Pandemonium Fortress", "City of the Damned", "River of Flame",
    "Harrogath", "Frigid Highlands", "Arreat Plateau", "Crystalline Passage", "Halls of Pain", "Glacial Trail", "Frozen Tundra", "The Ancients' Way", "Worldstone Keep Level 2",
]

def find_waypoints(raw: bytes) -> Optional[Waypoints]:
    idx = raw.find(WAYPOINT_MARKER)
    if idx == -1:
        return None
    start = idx + 8
    if start + 24*3 > len(raw):
        return None
    diffs: Dict[str, int] = {}
    for d_i, dname in enumerate(DIFFS):
        base = start + d_i*24
        bit_bytes = raw[base+2:base+7]
        if len(bit_bytes) != 5:
            return None
        diffs[dname] = int.from_bytes(bit_bytes, "little", signed=False)
    return Waypoints(offset=idx, difficulties=diffs)

def set_waypoint(raw: bytearray, wps: Waypoints, diff: str, wp_index: int, enabled: bool) -> None:
    if diff not in wps.difficulties:
        raise ValueError("Unknown difficulty")
    if not (0 <= wp_index < 39):
        raise ValueError("Waypoint index out of range")
    base = wps.offset + 8 + DIFFS.index(diff)*24
    b_off = base + 2
    bitfield = int.from_bytes(raw[b_off:b_off+5], "little", signed=False)
    if enabled:
        bitfield |= (1 << wp_index)
    else:
        bitfield &= ~(1 << wp_index)
    bitfield |= 1  # first waypoint always on
    raw[b_off:b_off+5] = int(bitfield & ((1<<40)-1)).to_bytes(5, "little", signed=False)
    wps.difficulties[diff] = bitfield
