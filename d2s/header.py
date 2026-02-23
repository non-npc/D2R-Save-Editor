from __future__ import annotations
from .models import Header
import re

# Known class IDs (0-6 original, 7+ D2R Reign of the Warlock)
CLASS_NAMES = {
    0: "Amazon",
    1: "Sorceress",
    2: "Necromancer",
    3: "Paladin",
    4: "Barbarian",
    5: "Druid",
    6: "Assassin",
    7: "Warlock",
}

def _u32(buf: bytes, off: int) -> int:
    return int.from_bytes(buf[off:off+4], "little", signed=False)

def parse_cstr_16(b: bytes) -> str:
    b = b.split(b"\x00", 1)[0]
    return b.decode("ascii", errors="ignore")

def encode_cstr_16(s: str) -> bytes:
    s = s.strip()
    if len(s) < 2:
        raise ValueError("Name must be at least 2 characters.")
    if len(s) > 15:
        raise ValueError("Name must be at most 15 characters.")
    if not s[0].isalpha():
        raise ValueError("Name must start with a letter.")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(ch not in allowed for ch in s):
        raise ValueError("Name contains invalid characters. Allowed: letters, digits, '-' and '_'")
    if s.count("-") + s.count("_") > 1:
        raise ValueError("Name may contain at most one '-' or '_' total.")
    raw = s.encode("ascii")
    return raw + b"\x00" * (16 - len(raw))

def _looks_like_name(s: str) -> bool:
    if not (2 <= len(s) <= 15):
        return False
    if not s[0].isalpha():
        return False
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,15}", s):
        return False
    if s.count("-") + s.count("_") > 1:
        return False
    return True

# D2R uses "skp " or "shp " (0x73 0x68 0x70 0x20) for character info block - both have same layout
_CHAR_BLOCK_TAGS = (b"skp ", b"shp ")

def _find_char_block(buf: bytes) -> int:
    """Return offset of 'skp ' or 'shp ' block, or -1 if not found."""
    for tag in _CHAR_BLOCK_TAGS:
        idx = buf.find(tag)
        if idx != -1:
            return idx
    return -1

def find_name_offset(buf: bytes, version: int = 0) -> tuple[int, int | None]:
    """
    Returns (name_offset, block_base).
    block_base is the offset of 'skp '/'shp ' tag if name was found via that block, else None.
    """
    # Try legacy offset first
    legacy = parse_cstr_16(buf[0x14:0x24])
    if _looks_like_name(legacy):
        return (0x14, None)

    # Newer saves: "skp " or "shp " block with name at +12 (v0x69) or +9 (some D2R Warlock saves)
    block = _find_char_block(buf)
    if block != -1:
        for name_off in (block + 12, block + 9):
            if name_off + 16 <= len(buf):
                cand = parse_cstr_16(buf[name_off:name_off + 16])
                if _looks_like_name(cand):
                    return (name_off, block)

    # D2R format (ver 0x69+): name at fixed offset 0x12B when no skp/shp (e.g. fresh Necromancer)
    # Both Warloxx and Brutus have names at 0x12B per analyze_saves.py
    if version >= 0x69 and 0x12B + 16 <= len(buf):
        cand = parse_cstr_16(buf[0x12B:0x12B + 16])
        if _looks_like_name(cand):
            return (0x12B, None)

    # Fallback: scan first ~800 bytes for a plausible 16-byte c-string name
    scan_max = min(len(buf) - 16, 1024)
    best = None
    for off in range(0, scan_max):
        b16 = buf[off:off+16]
        if 0 in b16:
            s = parse_cstr_16(b16)
            if _looks_like_name(s):
                # Prefer earlier offsets, but avoid trivial false positives by preferring offsets > 32 too
                score = off
                if best is None or score < best[0]:
                    best = (score, off)
    if best:
        return (best[1], None)

    # If all fails, default to legacy region to avoid crashing; name editing will likely fail validation anyway.
    return (0x14, None)

def parse_header(buf: bytes) -> Header:
    if len(buf) < 32:
        raise ValueError("File too small.")
    sig = _u32(buf, 0x00)
    ver = _u32(buf, 0x04)
    fsz = _u32(buf, 0x08)
    chk = _u32(buf, 0x0C)
    aw  = _u32(buf, 0x10)

    name_off, skp_base = find_name_offset(buf, version=ver)
    name = parse_cstr_16(buf[name_off:name_off+16])

    # Status byte: bits 2=Hardcore, 3=Died, 5=Expansion.
    # We only display Hardcore and Expansion (not Died) since D2R layout is uncertain.
    status = buf[0x24] if 0x24 < len(buf) else None
    prog = buf[0x25] if 0x25 < len(buf) else None

    # D2R format (version 0x69+): class at 0x18, level at 0x1B (not 0x28/0x2B classic)
    # Confirmed by comparing Warloxx.d2s (Warlock 92) vs Brutus.d2s (Necromancer 1)
    if ver >= 0x69 and 0x1B < len(buf):
        b = buf[0x18]
        if 0 <= b <= 15:
            char_class = b
            class_off = 0x18
        else:
            char_class = buf[0x28] if 0x28 < len(buf) else None
            class_off = 0x28 if (char_class is not None and 0 <= char_class <= 15) else None
        level = buf[0x1B]
        level_off = 0x1B if (1 <= level <= 99) else None
    else:
        char_class = buf[0x28] if 0x28 < len(buf) else None
        class_off = 0x28 if (char_class is not None and 0 <= char_class <= 15) else None
        level = buf[0x2B] if 0x2B < len(buf) else None
        level_off = 0x2B if (level is not None and 1 <= level <= 99) else None

    # D2R format: class may be in "skp "/"shp " block when legacy 0x28 invalid.
    # Search for block regardless of where name was found - name can be at legacy 0x14 while class
    # is only in the block (e.g. D2R Reign of the Warlock saves).
    # Scan block+4..block+8 (before name at +9); for +12 name layout scan to +11. Prefer 7 (Warlock).
    _BLOCK_CLASS_SCAN_END = 12
    if class_off is None:
        block = _find_char_block(buf)
        if block != -1:
            best_off, best_val = None, None
            for off in range(4, min(_BLOCK_CLASS_SCAN_END, len(buf) - block)):
                if buf[block + off] == 7:
                    best_off, best_val = block + off, 7
                    break  # Warlock found, use it
            if best_off is None:
                for off in range(4, min(_BLOCK_CLASS_SCAN_END, len(buf) - block)):
                    b = buf[block + off]
                    if 0 <= b <= 15:
                        best_off, best_val = block + off, b
                        if b != 0:
                            break  # prefer non-zero over 0
            if best_off is not None:
                char_class = best_val
                class_off = best_off

    # D2R Warlock: when legacy 0x28 has valid-looking class (e.g. 4=Barbarian) but block or kri
    # contains 7 (Warlock), prefer that - D2R format may store class there.
    if class_off is not None and char_class != 7:
        block = _find_char_block(buf)
        if block != -1:
            for off in range(4, min(_BLOCK_CLASS_SCAN_END, len(buf) - block)):
                if buf[block + off] == 7:
                    char_class = 7
                    class_off = block + off
                    break
        if char_class != 7:
            kri = buf.find(b"kri ")
            if kri != -1:
                for off in range(4, min(13, len(buf) - kri)):
                    if buf[kri + off] == 7:
                        char_class = 7
                        class_off = kri + off
                        break

    # Fallback: try "kri " block (character info?) - class may be at kri+4..kri+12
    if class_off is None:
        kri = buf.find(b"kri ")
        if kri != -1:
            best_off, best_val = None, None
            for off in range(4, min(13, len(buf) - kri)):
                b = buf[kri + off]
                if b == 7:
                    best_off, best_val = kri + off, 7
                    break
            if best_off is None:
                for off in range(4, min(13, len(buf) - kri)):
                    b = buf[kri + off]
                    if 0 <= b <= 15:
                        best_off, best_val = kri + off, b
                        break
            if best_off is not None:
                char_class = best_val
                class_off = best_off

    if class_off is None:
        char_class = None
    if level_off is None:
        level = None

    return Header(
        signature=sig,
        version=ver,
        file_size=fsz,
        checksum=chk,
        active_weapon=aw,
        name=name,
        name_offset=name_off,
        status=status,
        progression=prog,
        char_class=char_class,
        level=level,
        class_offset=class_off,
        level_offset=level_off,
    )

def apply_header_edits(raw: bytearray, hdr: Header, *, name: str | None = None, level: int | None = None, char_class: int | None = None) -> None:
    if name is not None:
        raw[hdr.name_offset:hdr.name_offset+16] = encode_cstr_16(name)
        hdr.name = name

    if char_class is not None:
        if hdr.class_offset is None:
            raise ValueError("Class offset is unknown for this save version; class editing disabled.")
        if not (0 <= char_class <= 15):
            raise ValueError("Class must be between 0 and 15.")
        raw[hdr.class_offset] = char_class
        hdr.char_class = char_class

    if level is not None:
        if hdr.level_offset is None:
            raise ValueError("Level offset is unknown for this save version; level editing disabled.")
        if not (1 <= level <= 99):
            raise ValueError("Level must be between 1 and 99.")
        raw[hdr.level_offset] = level
        hdr.level = level

def set_filesize(raw: bytearray) -> None:
    raw[0x08:0x0C] = len(raw).to_bytes(4, "little", signed=False)

def class_name(class_id: int | None) -> str:
    if class_id is None:
        return "Unknown"
    return CLASS_NAMES.get(class_id, f"Unknown({class_id})")
