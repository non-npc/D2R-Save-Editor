from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

@dataclass
class MarkerHit:
    name: str
    offset: int

@dataclass
class TagHit:
    tag: str
    offset: int
    length: Optional[int] = None  # if tag is length-prefixed, unknown for now

def find_markers(raw: bytes) -> List[MarkerHit]:
    markers = {
        "Skills (if)": b"if",
        "Quests (Woo!)": b"Woo!",
        "Waypoints (WS)": b"WS",
        "Items list (JM)": b"JM",
        "gf": b"gf",
    }
    hits: List[MarkerHit] = []
    for name, m in markers.items():
        start = 0
        while True:
            idx = raw.find(m, start)
            if idx == -1:
                break
            hits.append(MarkerHit(name=name, offset=idx))
            start = idx + 1
    hits.sort(key=lambda h: h.offset)
    return hits

def find_fourcc_tags(raw: bytes, scan_max: int = 4096) -> List[TagHit]:
    """
    Heuristically scan for 4-byte ASCII-ish tags (FourCC-like) followed by plausible structure.
    In newer D2R saves we've observed tags like:
      b'skp ', b'kri ', b'brs ', etc.
    We do NOT assume length encoding here; we just report offsets and show surrounding bytes in UI.
    """
    out: List[TagHit] = []
    scan_max = min(scan_max, len(raw) - 4)
    for off in range(0, scan_max):
        t = raw[off:off+4]
        # Accept letters/digits + space
        if all((32 <= b <= 126) for b in t):
            s = t.decode("ascii", errors="ignore")
            # Require at least 2 letters and allow trailing space
            if sum(ch.isalpha() for ch in s) >= 2 and s.strip() != "" and s[0].isalpha():
                # Reduce noise: require next 8 bytes to not be all printable (often binary data starts)
                # but allow either way; still reduce duplicates
                out.append(TagHit(tag=s, offset=off))
    # De-duplicate adjacent overlaps (sliding window creates many hits); keep only when tag changes
    out2: List[TagHit] = []
    last_off = -999
    last_tag = None
    for h in out:
        if h.offset - last_off < 4 and h.tag == last_tag:
            continue
        out2.append(h)
        last_off = h.offset
        last_tag = h.tag
    return out2
