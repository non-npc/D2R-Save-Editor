from __future__ import annotations
from typing import Optional
from .models import Skills

SKILLS_MARKER = b"if"  # per Trevin doc; used as an anchor

def find_skills(raw: bytes) -> Optional[Skills]:
    idx = raw.find(SKILLS_MARKER)
    if idx == -1:
        return None
    # Marker is 2 bytes; skills bytes follow immediately (30 bytes in classic layout)
    start = idx + 2
    end = start + 30
    if end > len(raw):
        return None
    values = list(raw[start:end])
    return Skills(offset=start, values=values)

def write_skills(raw: bytearray, skills: Skills) -> None:
    if skills.offset < 0 or skills.offset + 30 > len(raw):
        raise ValueError("Skills offset out of bounds.")
    if len(skills.values) != 30:
        raise ValueError("Skills must have exactly 30 values.")
    raw[skills.offset:skills.offset + 30] = bytes(int(v) & 0xFF for v in skills.values)
