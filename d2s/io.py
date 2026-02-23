from __future__ import annotations
import dataclasses
from typing import Optional
import os
from .models import SaveFile
from .header import parse_header, set_filesize
from .skills import find_skills
from .quests import find_quests
from .waypoints import find_waypoints
from .stats import find_stats
from .items import find_items
from .checksum import calculate_checksum, write_checksum

class D2SError(Exception):
    pass

def load_d2s(path: str) -> SaveFile:
    try:
        with open(path, "rb") as f:
            data = bytearray(f.read())
    except OSError as e:
        raise D2SError(str(e))

    hdr = parse_header(data)
    skills = find_skills(data)
    quests = find_quests(data)
    waypoints = find_waypoints(data)
    stats = find_stats(data)

    # D2R format: header may not have level; use stats block (stat_id 12 = Level)
    if hdr.level is None and stats is not None and 12 in stats.entries:
        hdr = dataclasses.replace(hdr, level=stats.entries[12].value)

    start_search = (skills.offset + 30) if skills is not None else 765
    items = find_items(bytes(data), start_search=start_search)

    return SaveFile(raw=data, header=hdr, skills=skills, quests=quests, waypoints=waypoints, stats=stats, items=items, path=path)

def verify(save: SaveFile) -> bool:
    expected = save.header.checksum
    actual = calculate_checksum(bytes(save.raw))
    return (expected & 0xFFFFFFFF) == (actual & 0xFFFFFFFF)

def save_d2s(save: SaveFile, path: Optional[str] = None, make_backup: bool = True) -> None:
    out_path = path or save.path
    if not out_path:
        raise D2SError("No output path specified.")

    if make_backup:
        try:
            if os.path.exists(out_path):
                import shutil
                shutil.copy2(out_path, out_path + ".bak")
        except Exception:
            pass

    set_filesize(save.raw)
    write_checksum(save.raw)

    try:
        with open(out_path, "wb") as f:
            f.write(save.raw)
    except OSError as e:
        raise D2SError(str(e))
