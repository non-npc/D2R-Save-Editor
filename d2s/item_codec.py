"""Full bit-level item codec for D2R saves (item format v97+).

Ported from the dschu012/d2s reference implementation (items.js), with the
same LSB-first bit order and field layout. Every parsed item records the bit
positions of its fields so values can later be patched **in place** (never
re-serializing the file), which keeps everything else byte-identical.

Editing safety rules:
  * Only magic-property values with no special encoding are editable
    (no params `sP`, no packed charges `e == 3`).
  * Adding/deleting props (`add_magic_prop_ex` / `delete_magic_prop`) splices
    the bit stream: everything after the item's prop list shifts, so callers
    must re-parse and rewrite the checksum afterwards.
  * Callers must work on a copy of the raw bytes and rewrite the checksum.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .bitstream import BitStream

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_CONSTANTS_PATH = os.path.join(_DATA_DIR, "constants_99.json")

_CONSTANTS: Optional[dict] = None
_I18N: Optional[dict] = None

# Item category -> type_id (mirrors JS ItemType)
ARMOR, SHIELD, WEAPON, OTHER = 1, 2, 3, 4
QUALITY_NAMES = {
    1: "Low Quality", 2: "Normal", 3: "Superior", 4: "Magic",
    5: "Set", 6: "Rare", 7: "Unique", 8: "Crafted",
}

# Huffman tree for 4-char item type codes (D2R, item version >= 0x61)
HUFFMAN = [[[[["w", "u"], [["8", ["y", ["5", ["j", []]]]], "h"]], ["s", [["2", "n"], "x"]]], [[["c", ["k", "f"]], "b"], [["t", "m"], ["9", "7"]]]], [" ", [[[["e", "d"], "p"], ["g", [[["z", "q"], "3"], ["v", "6"]]]], [["r", "l"], ["a", [["1", ["4", "0"]], ["i", "o"]]]]]]]

# Encoding lookup table: char -> (bit value, bit length) — consistent with the
# tree above (from dschu012/d2s items.js).
HUFFMAN_LOOKUP = {
    "0": (223, 8), "1": (31, 7), "2": (12, 6), "3": (91, 7), "4": (95, 8),
    "5": (104, 8), "6": (123, 7), "7": (30, 5), "8": (8, 6), "9": (14, 5),
    " ": (1, 2), "a": (15, 5), "b": (10, 4), "c": (2, 5), "d": (35, 6),
    "e": (3, 6), "f": (50, 6), "g": (11, 5), "h": (24, 5), "i": (63, 7),
    "j": (232, 9), "k": (18, 6), "l": (23, 5), "m": (22, 5), "n": (44, 6),
    "o": (127, 7), "p": (19, 5), "q": (155, 8), "r": (7, 5), "s": (4, 4),
    "t": (6, 5), "u": (16, 5), "v": (59, 7), "w": (0, 5), "x": (28, 5),
    "y": (40, 7), "z": (27, 8),
}

def encode_type_code(t: str) -> List[int]:
    """4-char type code -> LSB-first bit sequence."""
    bits = []
    for ch in t:
        v, l = HUFFMAN_LOOKUP[ch]
        for i in range(l):
            bits.append((v >> i) & 1)
    return bits

# Gem tier chain: chipped -> flawed -> normal -> flawless -> perfect
# (code suffix = kind: v amethyst / r ruby / g emerald / b sapphire / y topaz);
# skulls: skc/skf/sks/skl/skz.
# Tier prefixes from the official zh-CN string table, in tier order. Tiers are
# matched by display name, not by code letters — Infernal's code scheme differs
# from classic D2. (Localization data for the generated zh-CN table; tier 2 =
# the bare base name with no prefix.)
GEM_TIER_PREFIXES_ZH = (("完美的", 4), ("无瑕的", 3), ("有瑕疵的", 1), ("碎裂的", 0))
GEM_KEYWORDS_ZH = {"gem": "宝石", "skull": "头骨", "rune": "神符", "jewel": "珠宝"}

def gem_tiers(constants: Optional[dict] = None) -> dict:
    """Gem upgrade chains: {current code: next tier code}.
    Tiers and kinds are recognized by official display names (e.g. Chipped
    Amethyst / Flawed Amethyst / Amethyst / Flawless Amethyst / Perfect
    Amethyst); entries of the same base name are linked in tier order. Modded
    item codes don't matter (names come from the game string tables).
    Falls back to grouping by official English names when the i18n table has
    not been generated (works in upstream English environments too)."""
    constants = constants or load_constants()
    i18n = load_i18n()
    items = i18n.get("items", {})
    groups = {}
    kw = GEM_KEYWORDS_ZH
    for key, zh in items.items():
        if key.startswith("en:") or len(key) != 3:
            continue
        if (kw["gem"] not in zh and kw["skull"] not in zh) or kw["rune"] in zh or kw["jewel"] in zh:
            continue
        tier, base = 2, zh
        for pfx, t in GEM_TIER_PREFIXES_ZH:
            if zh.startswith(pfx):
                tier, base = t, zh[len(pfx):]
                break
        groups.setdefault(base, []).append((tier, key, zh))
    chains = {}
    for base, lst in groups.items():
        lst.sort()
        for a, b in zip(lst, lst[1:]):
            chains[a[1]] = b[1]
    if chains:
        return chains

    # English fallback: when no i18n table was generated, group by the official
    # English names from constants (Chipped/Flawed/Flawless/Perfect prefixes +
    # bare base names) so gem upgrades work in English environments too.
    misc = constants.get("other_items", {})
    en_groups = {}
    for code, det in misc.items():
        n = (det or {}).get("n") or ""
        tier = base = None
        for pfx, t in (("Chipped ", 0), ("Flawed ", 1), ("Perfect ", 4), ("Flawless ", 3)):
            if n.startswith(pfx):
                tier, base = t, n[len(pfx):]
                break
        if tier is None and n in ("Amethyst", "Diamond", "Emerald", "Ruby", "Sapphire", "Topaz", "Skull"):
            tier, base = 2, n
        if tier is None or not base:
            continue
        en_groups.setdefault(base, []).append((tier, code))
    chains = {}
    for base, lst in en_groups.items():
        lst.sort()
        for a, b in zip(lst, lst[1:]):
            chains[a[1]] = b[1]
    return chains


def load_constants() -> dict:
    global _CONSTANTS
    if _CONSTANTS is None:
        with open(_CONSTANTS_PATH, "r", encoding="utf-8") as f:
            c = json.load(f)
        # JSON object keys are strings; restore int keys where the JS code
        # used numeric indexes. Some tables are plain arrays (index = id).
        for key in ("unq_items", "set_items", "runewords"):
            if isinstance(c[key], dict):
                c[key] = {int(k): v for k, v in c[key].items()}
        # D2R new format: rejuvenation potions carry a "fullness" quantity
        # field missing from the classic tables (verified on a v105 save)
        stack = c.setdefault("stackables", {})
        for t in ("rvs", "rvl"):
            stack.setdefault(t, {"n": "Rejuvenation Potion"})
        _CONSTANTS = c
    return _CONSTANTS


def load_i18n() -> dict:
    """Optional zh-CN display table (one-way mapping: display only, never
    affects any data written back to the save). Empty dict when the user has
    not generated d2s/data/i18n_zh.json (via tools/build_i18n.py)."""
    global _I18N
    if _I18N is None:
        path = os.path.join(_DATA_DIR, "i18n_zh.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                _I18N = json.load(f)
        else:
            _I18N = {}
    return _I18N


def _zh_item(code_or_en: str) -> Optional[str]:
    i18n = load_i18n()
    items = i18n.get("items", {})
    z = items.get(code_or_en)
    if z:
        return z
    return items.get("en:" + code_or_en)


def _by_id(table, idx: int) -> dict:
    """Lookup in a table that may be a list (index = id) or an int-keyed dict."""
    if idx is None:
        return {}
    if isinstance(table, list):
        return table[idx] if 0 <= idx < len(table) and table[idx] else {}
    return table.get(idx, {})


# ---------------------------------------------------------------------------
# low-level helpers

def _read_type_code_huffman(bs: BitStream) -> str:
    out = ""
    for _ in range(4):
        node = HUFFMAN
        while isinstance(node, list):
            node = node[bs.read_bits(1)]
        out += node
    return out.replace("\0", "").strip()


def _get_item_details(item_type: str, constants: dict) -> Optional[dict]:
    for table in ("armor_items", "weapon_items", "other_items"):
        if item_type in constants[table]:
            return constants[table][item_type]
    return None


def _mp(stat_id: int, constants: dict) -> dict:
    return constants["magical_properties"][stat_id]


# ---------------------------------------------------------------------------
# magic properties

def read_magic_properties(bs: BitStream, constants: dict) -> List[dict]:
    """Reads a 0x1FF-terminated magic property list; records each plain value's
    bit position so it can be patched in place later."""
    props: List[dict] = []
    mp_all = constants["magical_properties"]
    _dbg = os.environ.get("D2S_DEBUG")
    if _dbg:
        print(f"      props start {bs.tell()}")
    while True:
        prop_start = bs.tell()
        id_ = bs.read_bits(9)
        if _dbg:
            print(f"      prop id={id_} @{bs.tell()-9}", end="")
        if id_ == 0x1FF:
            if _dbg:
                print(" -> terminator")
            break
        if _dbg:
            print()
        if id_ >= len(mp_all):
            raise ValueError(f"Invalid stat id {id_} at bit {bs.tell() - 9}")
        prop_out = {"id": id_, "name": mp_all[id_]["s"], "fields": [],
                    "_start_bit": prop_start}  # position before the id (for splice/delete)
        num = mp_all[id_].get("np") or 1
        for i in range(num):
            sub = mp_all[id_ + i]
            field = {"stat_id": id_ + i, "name": sub["s"], "editable": False}
            sp = sub.get("sP")
            if sp:
                param = bs.read_bits(sp)
                if sub.get("dF") == 14:  # +skill to skilltab
                    prop_out["values"] = prop_out.get("values", [])
                    prop_out.setdefault("values", []).append(param & 0x7)
                    param = (param >> 3) & 0x1FFF
                elif sub.get("e") in (2, 3):  # chance to cast / charges
                    prop_out.setdefault("values", []).append(param & 0x3F)
                    param = (param >> 6) & 0x3FF
                field["param"] = param
                field["editable"] = False
            if not sub.get("sB"):
                raise ValueError(f"Stat {id_}:{sub['s']} has no save bits")
            bits = sub["sB"]
            field["bits"] = bits
            field["value_bitpos"] = bs.tell()
            v = bs.read_bits(bits)
            sa = sub.get("sA") or 0
            field["sA"] = sa
            if sub.get("e") == 3:  # charges: low byte current, high byte max
                field["editable"] = False
                field["charges"] = {"cur": v & 0xFF, "max": (v >> 8) & 0xFF}
                field["value"] = v & 0xFF  # expose current charges (read-only)
            else:
                v -= sa
                field["value"] = v
                field["editable"] = not sp
            prop_out["fields"].append(field)
        prop_out["_end_bit"] = bs.tell()  # position after the whole group (all np parts)
        props.append(prop_out)
    return props


def patch_magic_value(raw: bytearray, prop_field: dict, new_value: int) -> None:
    """In-place patch of one editable plain value (same bit width)."""
    if not prop_field.get("editable"):
        raise ValueError("This field uses a special encoding and cannot be patched.")
    bits = prop_field["bits"]
    if not (0 <= new_value < (1 << bits)):
        raise ValueError(f"Value out of range 0..{(1 << bits) - 1}")
    bs = BitStream(raw, prop_field["value_bitpos"])
    bs.set_bits(prop_field["value_bitpos"], bits, new_value + prop_field.get("sA", 0))


# Parametric prop whitelist: param_kind -> parameter semantics for UI/insertion
#   skill:     param = skill id (e.g. item_singleskill +X to a skill)
#   class:     param = class id (0..7, item_addclassskills)
#   tab_skill: param = (skill tab, skill id), dF==14 packs tab(3 bits)|skill(13 bits)<<3
#   cast:      param = (level, skill id), e==2 packs level(6 bits)|skill(10 bits)<<6,
#              value = chance %
#   charges:   param = (level, skill id), value = (current, max) charges packed cur|max<<8
_PARAM_PROPS = {
    83: "class",      # item_addclassskills
    97: "skill",      # item_nonclassskill
    107: "skill",     # item_singleskill
    151: "skill",     # item_aura
    188: "tab_skill",  # item_addskill_tab (dF==14)
    195: "cast", 196: "cast", 197: "cast", 198: "cast", 199: "cast", 201: "cast",
    204: "charges",   # item_charged_skill
}

# Neutral dropdown labels for stats whose official templates hardcode a
# specific param value (stat 83 dP hardcodes Amazon, stat 188 hardcodes the
# Javelin/Spear tab). English fallbacks; zh-CN overrides come from the
# generated table's "ui" section (prop_neutral_83 / prop_neutral_188). The
# per-prop table display after insertion still shows the official template for
# the actual param (see describe_magic_prop for stat 83).
_NEUTRAL_DESC_EN = {83: "%+d to Class Skill Levels", 188: "%+d to Skill Tab Skills"}


def list_addable_props(constants: Optional[dict] = None) -> List[dict]:
    """Props that can be added: plain value props + parametric props
    (skill / class / skill tab / chance-to-cast / charged).
    Returns [{id, name, desc, sB, sA, min, max, param_kind, param_bits}],
    sorted for display. desc prefers the official zh-CN template from the
    generated table (i18n stat_tpl) and falls back to the constants table's
    English dP/dN. param_kind None = plain value prop; otherwise see the
    _PARAM_PROPS comment. Still excluded: np multi-part group props and props
    with unsupported param semantics (state/montype/reanimate etc.)."""
    constants = constants or load_constants()
    i18n = load_i18n()
    stat_tpl = i18n.get("stat_tpl", {})
    ui = i18n.get("ui", {})
    neutral_desc = {i: ui.get(f"prop_neutral_{i}") or en
                    for i, en in _NEUTRAL_DESC_EN.items()}
    out = []
    for i, p in enumerate(constants["magical_properties"]):
        param_kind = _PARAM_PROPS.get(i)
        if not p or p.get("np"):
            continue
        if p.get("sP") and param_kind is None:
            continue  # has a param but unsupported semantics (state/montype/reanimate/elemskill...)
        if not p.get("sP") and p.get("e") in (1, 2, 3):
            continue
        sB = p.get("sB")
        if not sB or sB > 21:  # skip overly wide / abnormal widths
            continue
        desc_en = p.get("dP") or p.get("dN")
        if not desc_en:
            continue
        desc = stat_tpl.get(str(i)) or desc_en
        if i in neutral_desc:
            desc = neutral_desc[i]
        sA = p.get("sA", 0) or 0
        entry = {
            "id": i,
            "name": p["s"],
            "desc": desc.replace("%%", "%"),
            "sB": sB,
            "sA": sA,
            "min": -sA,
            "max": (1 << sB) - 1 - sA,
            "param_kind": param_kind,
            "param_bits": p.get("sP"),
        }
        if param_kind == "charges":  # value = (current, max) charges, 8 bits each
            entry["min"], entry["max"] = 1, 255
        out.append(entry)
    out.sort(key=lambda x: (x["id"] > 100, x["desc"].lower()))
    return out


def _pack_param(sub: dict, param) -> Optional[int]:
    """Pack a param into its raw sP-bit value per the encoding rules; returns
    None for props without sP. param: None / int (raw skill id, class id, ...)
    / a 2-tuple:
      - dF==14: (tab, skill_id) -> tab | skill<<3
      - e in (2,3): (level, skill_id) -> level | skill<<6"""
    sp = sub.get("sP")
    if not sp:
        if param is not None:
            raise ValueError(f"{sub['s']} has no param field; a param must not be given")
        return None
    dfv = sub.get("dF")
    enc = sub.get("e")
    if dfv == 14:
        tab, skill = param
        p = (tab & 0x7) | ((skill & 0x1FFF) << 3)
    elif enc in (2, 3):
        level, skill = param
        p = (level & 0x3F) | ((skill & 0x3FF) << 6)
    else:
        p = int(param)
    if not (0 <= p < (1 << sp)):
        raise ValueError(f"Param out of range 0..{(1 << sp) - 1} (prop {sub['s']})")
    return p


def _pack_value(sub: dict, value) -> int:
    """Display value -> stored raw value (adds the sA offset). For e==3 charges
    pass (current, max); packed = cur+base | max<<8 (same as items.js)."""
    sA = sub.get("sA", 0) or 0
    sB = sub.get("sB")
    if not sB:
        raise ValueError(f"Prop {sub['s']} has no bit width and cannot be added")
    if sub.get("e") == 3:
        cur, mx = value
        cur, mx = int(cur), int(mx)
        if not (0 <= cur <= 255 and 0 <= mx <= 255):
            raise ValueError("Charges out of range 0..255")
        v = (cur + sA) | ((mx & 0xFF) << 8)
    else:
        v = int(value) + sA
    if not (0 <= v < (1 << sB)):
        raise ValueError(f"Value out of range {[-sA, (1 << sB) - 1 - sA]} (prop {sub['s']})")
    return v


def _encode_prop_bits(prop_id: int, fields_spec: list, constants: dict) -> List[int]:
    """Encode one prop as an LSB-first bit list: id(9) + each part's param(sP)+value(sB)."""
    mp = constants["magical_properties"]
    if not (0 <= prop_id < len(mp)) or not mp[prop_id]:
        raise ValueError(f"Unknown prop id: {prop_id}")
    sub0 = mp[prop_id]
    num = sub0.get("np") or 1  # np group: fields_spec carries one (param, value) pair per part
    if len(fields_spec) != num:
        raise ValueError(f"This prop needs {num} (param, value) pair(s), got {len(fields_spec)}")
    bits = [(prop_id >> i) & 1 for i in range(9)]
    for i in range(num):
        sub = mp[prop_id + i]
        packed = _pack_param(sub, fields_spec[i][0])
        if packed is not None:
            bits.extend((packed >> k) & 1 for k in range(sub["sP"]))
        v = _pack_value(sub, fields_spec[i][1])
        bits.extend((v >> k) & 1 for k in range(sub["sB"]))
    return bits


def _trailing_prop_bits_end(item: dict) -> int:
    """Actual data end bit after the prop terminator, before the alignment
    padding (includes set/runeword attribute lists). When splicing the prop
    list the old padding is discarded and re-aligned to the new length so no
    stray bytes remain."""
    end = item["_term_bitpos"] + 9  # after the 9-bit terminator
    lists = list(item.get("set_attributes") or []) + [item.get("runeword_attributes")]
    for lst in lists:
        for p in lst or []:
            pe = p.get("_end_bit")
            if pe:
                end = max(end, pe)
    return min(end, item["_end_bit"])


def add_magic_prop_ex(raw: bytearray, item: dict, prop_id: int, fields_spec: list,
                      constants: Optional[dict] = None) -> None:
    """Insert an arbitrary prop into an item's prop list (bit-stream surgery;
    the general version of add_magic_prop):
      [prefix low bits][original prop bits kept bit-by-bit][new prop bits]
      [terminator + set/runeword attribute bits kept bit-by-bit][padding][original tail data]
    fields_spec: [(param or None, value), ...] in sub-field order; encoding
    rules in _pack_param/_pack_value.
    Old alignment padding is discarded and re-padded to the new length (the
    next item stays byte-aligned, no stray bytes). Callers must re-parse /
    save afterwards (saving fixes the checksum automatically)."""
    constants = constants or load_constants()
    new_bits = _encode_prop_bits(prop_id, fields_spec, constants)
    start = item["_props_start_bit"]
    term = item["_term_bitpos"]
    data_end = _trailing_prop_bits_end(item)

    old_bits = [(raw[p // 8] >> (p % 8)) & 1 for p in range(start, term)]
    tail_bits = [(raw[p // 8] >> (p % 8)) & 1 for p in range(term, data_end)]

    prefix_bytes = start // 8
    low_bits_n = start % 8
    prefix = bytes(raw[:prefix_bytes])
    low_bits = [(raw[prefix_bytes] >> i) & 1 for i in range(low_bits_n)] if low_bits_n else []

    all_bits = low_bits + old_bits + new_bits + tail_bits
    while len(all_bits) % 8:
        all_bits.append(0)
    packed = bytearray()
    for i in range(0, len(all_bits), 8):
        b = 0
        for j, bit in enumerate(all_bits[i:i + 8]):
            b |= bit << j
        packed.append(b)

    new_raw = bytearray(prefix) + packed + bytearray(raw[item["_end_bit"] // 8:])
    raw[:] = new_raw


def add_magic_prop(raw: bytearray, item: dict, prop_id: int, value: int,
                   constants: Optional[dict] = None) -> None:
    """Insert a plain-value prop into an item's prop list (compatibility entry
    point; internally delegates to add_magic_prop_ex).
    Bit layout: [original prop bits kept bit-by-bit] + [new prop bits]
    + [9-bit terminator] + [padding] + [original tail data].
    Callers must re-parse / save afterwards (saving fixes the checksum)."""
    constants = constants or load_constants()
    sub = constants["magical_properties"][prop_id]
    if sub.get("sP") or sub.get("np") or sub.get("e") in (1, 2, 3):
        raise ValueError("This prop uses a special encoding and cannot be added here "
                         "(use add_magic_prop_ex for non-plain props)")
    if not sub.get("sB"):
        raise ValueError("This prop has no bit width and cannot be added")
    add_magic_prop_ex(raw, item, prop_id, [(None, value)], constants)


def delete_magic_prop(raw: bytearray, item: dict, prop: dict,
                      constants: Optional[dict] = None) -> None:
    """Delete one prop from an item's prop list (whole np group; bit-stream
    surgery, the mirror image of insertion):
      [prefix low bits][props_start..prop._start_bit kept as-is]
      [prop._end_bit..terminator/set attributes kept as-is]
      + [padding] + [original tail data]
    Old alignment padding is discarded and re-padded to the new length
    (deleting a prop inserted earlier restores the exact bytes). Callers must
    re-parse / save afterwards (saving fixes the checksum)."""
    start = item["_props_start_bit"]
    term = item["_term_bitpos"]
    data_end = _trailing_prop_bits_end(item)
    ps = prop.get("_start_bit")
    pe = prop.get("_end_bit")
    if ps is None or pe is None:
        raise ValueError("Prop lacks bit position info; reload the save and try again")
    if not (start <= ps < pe <= term):
        raise ValueError("Prop bit positions look wrong (possibly from the set/runeword "
                         "attribute lists); deletion refused")

    prefix_bytes = start // 8
    low_bits_n = start % 8
    prefix = bytes(raw[:prefix_bytes])
    low_bits = [(raw[prefix_bytes] >> i) & 1 for i in range(low_bits_n)] if low_bits_n else []
    keep1 = [(raw[p // 8] >> (p % 8)) & 1 for p in range(start, ps)]
    keep2 = [(raw[p // 8] >> (p % 8)) & 1 for p in range(pe, data_end)]

    all_bits = low_bits + keep1 + keep2
    while len(all_bits) % 8:
        all_bits.append(0)
    packed = bytearray()
    for i in range(0, len(all_bits), 8):
        b = 0
        for j, bit in enumerate(all_bits[i:i + 8]):
            b |= bit << j
        packed.append(b)

    new_raw = bytearray(prefix) + packed + bytearray(raw[item["_end_bit"] // 8:])
    raw[:] = new_raw


def change_item_type(raw: bytearray, item: dict, new_type: str,
                     constants: Optional[dict] = None,
                     span_end: Optional[int] = None) -> None:
    """Change a simple item's type code (rebase; e.g. gem tier upgrade
    gcv -> gpv, or rune r07 -> r33). Bit-stream surgery: replaces the type
    code bits (variable-length Huffman) and shifts everything after; callers
    must re-parse / save. Only supports simple items (potions/gems/scrolls...).

    span_end: end of the bit span the item actually occupies in the file
    (byte-aligned). D2R appends a zero alignment/stack byte after some simple
    items (gems/runes etc.), visible as the next item's _start_bit sitting 8
    bits after this item's _end_bit. When span_end is given (= the next
    item's _start_bit), the type-code length change is absorbed inside the
    item's span:
      - growing (delta>0): paid for with the trailing zero byte(s) of the
        span (refused if they are not zero); the item's total span is
        unchanged and every other byte stays untouched — safe in game;
      - shrinking/equal (delta<=0): zero-padded to the end of the span,
        span unchanged.
    When omitted (None) the old behavior applies: shift at item['_end_bit']
    (equal-length conversions like gem upgrades are unaffected; growing ones
    shift the file tail, kept for existing callers)."""
    if item.get("simple_item") != 1:
        raise ValueError("Only simple items (gems/potions/scrolls etc.) support type change")
    tb = item.get("_type_bits")
    if not tb:
        raise ValueError("Item lacks type bit info; reload the save")
    if len(new_type) != 4:
        new_type = (new_type + "    ")[:4]
    for ch in new_type.strip() or " ":
        if ch not in HUFFMAN_LOOKUP:
            raise ValueError(f"Type code contains an unencodable character: {ch!r}")

    t_start, t_end = tb
    new_code_bits = encode_type_code(new_type)
    delta = len(new_code_bits) - (t_end - t_start)
    end = item["_end_bit"]
    if span_end is None:
        span_end = end
    if not (t_end <= end <= span_end <= len(raw) * 8) or span_end % 8:
        raise ValueError("Item bit span info looks wrong; reload the save and try again")
    if delta > 0:
        trim = 8 * ((delta + 7) // 8)  # zero bytes needed to absorb the growth
        if span_end - end < trim:
            raise ValueError(
                "Not enough zero padding bytes at the item's tail to absorb the "
                "longer type code; cannot convert safely (move the item / reload "
                "the save and try again)")
        for p in range(span_end - trim, span_end):
            if (raw[p // 8] >> (p % 8)) & 1:
                raise ValueError("Trailing padding bytes are not zero; conversion refused "
                                 "to avoid corrupting the item")
        end = span_end - trim
    else:
        end = span_end

    prefix_bytes = t_start // 8
    low_bits_n = t_start % 8
    prefix = bytes(raw[:prefix_bytes])
    low_bits = [(raw[prefix_bytes] >> i) & 1 for i in range(low_bits_n)] if low_bits_n else []
    keep = [(raw[p // 8] >> (p % 8)) & 1 for p in range(t_end, end)]

    all_bits = low_bits + new_code_bits + keep
    while len(all_bits) % 8:
        all_bits.append(0)
    packed = bytearray()
    for i in range(0, len(all_bits), 8):
        b = 0
        for j, bit in enumerate(all_bits[i:i + 8]):
            b |= bit << j
        packed.append(b)

    if span_end is not None and prefix_bytes * 8 + len(packed) * 8 != span_end:
        raise ValueError("Cannot re-align to the original item span after the type code "
                         "conversion (aborted, nothing written)")
    new_raw = bytearray(prefix) + packed + bytearray(raw[span_end // 8:])
    raw[:] = new_raw


# ---------------------------------------------------------------------------
# items

def _read_simple_bits(item: dict, bs: BitStream, version: int, constants: dict) -> None:
    if os.environ.get("D2S_DEBUG"):
        print(f"    [item @ {bs.tell()}]")
    item["unknown_b0_3"] = bs.read_bits(4)
    item["identified"] = bs.read_bits(1)
    item["unknown_b5_10"] = bs.read_bits(6)
    item["socketed"] = bs.read_bits(1)
    item["unknown_b12"] = bs.read_bits(1)
    item["new"] = bs.read_bits(1)
    item["unknown_b14_15"] = bs.read_bits(2)
    item["is_ear"] = bs.read_bits(1)
    item["starter_item"] = bs.read_bits(1)
    item["unknown_b18_20"] = bs.read_bits(3)
    item["simple_item"] = bs.read_bits(1)
    item["ethereal"] = bs.read_bits(1)
    item["unknown_b23"] = bs.read_bits(1)
    item["personalized"] = bs.read_bits(1)
    item["unknown_b25"] = bs.read_bits(1)
    item["given_runeword"] = bs.read_bits(1)
    item["unknown_b27_31"] = bs.read_bits(5)
    if version >= 0x61:
        item["item_version"] = bs.read_bits(3)
    item["location_id"] = bs.read_bits(3)
    item["equipped_id"] = bs.read_bits(4)
    item["position_x"] = bs.read_bits(4)
    item["position_y"] = bs.read_bits(4)
    item["alt_position_id"] = bs.read_bits(3)
    if item["is_ear"]:
        ear = {"class": bs.read_bits(3), "level": bs.read_bits(7), "name": ""}
        chars = []
        for _ in range(15):
            ch = bs.read_bits(7)
            if ch == 0:
                break
            chars.append(chr(ch))
        ear["name"] = "".join(chars)
        item["ear_attributes"] = ear
        item["type"] = "ear"
        return
    if version >= 0x61:
        _type_start = bs.tell()
        item["type"] = _read_type_code_huffman(bs)
        item["_type_bits"] = (_type_start, bs.tell())
    else:
        _type_start = bs.tell()
        item["type"] = "".join(chr(bs.read_bits(8)) for _ in range(4)).strip().replace("\0", "")
        item["_type_bits"] = (_type_start, bs.tell())
    if os.environ.get("D2S_DEBUG"):
        print(f"    type={item['type']!r} @ bit {bs.tell()}")
    details = _get_item_details(item["type"], constants)
    item["categories"] = (details or {}).get("c") or []
    item["base_name"] = (details or {}).get("n") or item["type"]
    if "Any Armor" in item["categories"]:
        item["type_id"] = ARMOR
    elif "Weapon" in item["categories"]:
        item["type_id"] = WEAPON
    else:
        item["type_id"] = OTHER
    bits = 3  # D2R v105: socket count is 3 bits for simple items too
    if "Quest" in item["categories"]:
        item["quest_difficulty"] = bs.read_bits(_mp(356, constants)["sB"])
        bits = 1
    item["nr_of_items_in_sockets"] = bs.read_bits(bits)
    # simple items with a quantity (rejuvenation potion fullness etc.) carry the
    # quantity field right after
    if item["simple_item"] and item["type"] in constants.get("stackables", {}):
        item["_qty_field"] = {
            "name": "quantity", "value_bitpos": bs.tell(), "bits": 9,
            "sA": 0, "editable": True,
        }
        item["quantity"] = bs.read_bits(9)
        item["_qty_field"]["value"] = item["quantity"]


def parse_item(bs: BitStream, version: int, constants: dict) -> dict:
    item: dict = {"_start_bit": bs.tell()}
    _read_simple_bits(item, bs, version, constants)
    if not item["simple_item"]:
        item["id"] = bs.read_bits(32)
        item["item_level"] = bs.read_bits(7)
        item["quality"] = bs.read_bits(4)
        if bs.read_bits(1):  # multiple pictures
            item["picture_id"] = bs.read_bits(3)
        if bs.read_bits(1):  # class specific
            item["auto_affix_id"] = bs.read_bits(11)
        q = item["quality"]
        if q == 1:  # low quality
            item["low_quality_id"] = bs.read_bits(3)
        elif q == 3:  # superior
            item["file_index"] = bs.read_bits(3)
        elif q == 4:  # magic
            pre = bs.read_bits(11)
            item["magic_prefix"] = pre or None
            suf = bs.read_bits(11)
            item["magic_suffix"] = suf or None
        elif q == 5:  # set
            item["set_id"] = bs.read_bits(12)
        elif q == 7:  # unique
            item["unique_id"] = bs.read_bits(12)
        elif q in (6, 8):  # rare / crafted
            item["rare_name_id"] = bs.read_bits(8)
            item["rare_name_id2"] = bs.read_bits(8)
            item["magical_name_ids"] = [
                bs.read_bits(11) if bs.read_bits(1) else None
                for _ in range(6)
            ]
        if item["given_runeword"]:
            item["runeword_id"] = bs.read_bits(12)
            if item["runeword_id"] == 2718:
                item["runeword_id"] = 48
            bs.read_bits(4)  # always 5
        if item["personalized"]:
            chars = []
            for _ in range(16):
                ch = bs.read_bits(8 if version > 0x61 else 7)
                if ch == 0:
                    break
                chars.append(chr(ch))
            item["personalized_name"] = "".join(chars)
        if item["type"] in ("tbk", "ibk"):  # tomes
            bs.read_bits(5)
        item["timestamp"] = bs.read_bits(1)
        if item["type_id"] == ARMOR:
            mp = _mp(31, constants)
            item["_defense_field"] = {
                "name": "defense", "value_bitpos": bs.tell(), "bits": mp["sB"],
                "sA": mp.get("sA", 0), "editable": True,
            }
            item["defense_rating"] = bs.read_bits(mp["sB"]) - mp.get("sA", 0)
            item["_defense_field"]["value"] = item["defense_rating"]
        if item["type_id"] in (ARMOR, WEAPON):
            mp = _mp(73, constants)
            item["_durmax_field"] = {
                "name": "maxdurability", "value_bitpos": bs.tell(), "bits": mp["sB"],
                "sA": mp.get("sA", 0), "editable": True,
            }
            item["max_durability"] = bs.read_bits(mp["sB"]) - mp.get("sA", 0)
            item["_durmax_field"]["value"] = item["max_durability"]
            if item["max_durability"] > 0:
                mp = _mp(72, constants)
                item["_durcur_field"] = {
                    "name": "durability", "value_bitpos": bs.tell(), "bits": mp["sB"],
                    "sA": mp.get("sA", 0), "editable": True,
                }
                item["current_durability"] = bs.read_bits(mp["sB"]) - mp.get("sA", 0)
                item["_durcur_field"]["value"] = item["current_durability"]
        if item["type"] in constants.get("stackables", {}):
            item["_qty_field"] = {
                "name": "quantity", "value_bitpos": bs.tell(), "bits": 9,
                "sA": 0, "editable": True,
            }
            item["quantity"] = bs.read_bits(9)
            item["_qty_field"]["value"] = item["quantity"]
        if item["socketed"] == 1:
            item["total_nr_of_sockets"] = bs.read_bits(4)
        plist_flag = 0
        if item["quality"] == 5:  # set
            plist_flag = bs.read_bits(5)
        item["_preprop_bitpos"] = bs.tell()
        bs.read_bits(1)  # v105: unknown 1-bit field before magic properties (observed empirically)
        item["_props_start_bit"] = bs.tell()
        item["magic_attributes"] = read_magic_properties(bs, constants)
        item["_term_bitpos"] = bs.tell() - 9  # 9-bit 0x1FF terminator position
        if plist_flag:
            item["set_attributes"] = []
            while plist_flag:
                if plist_flag & 1:
                    item["set_attributes"].append(read_magic_properties(bs, constants))
                plist_flag >>= 1
        if item["given_runeword"] == 1:
            item["runeword_attributes"] = read_magic_properties(bs, constants)
    # byte align, then socket children follow at byte boundary
    if bs.tell() % 8:
        bs.seek((bs.tell() // 8 + 1) * 8)
    item["_end_bit"] = bs.tell()
    if item.get("nr_of_items_in_sockets", 0) > 0 and not item["simple_item"]:
        item["socketed_items"] = [
            parse_item(bs, version, constants)
            for _ in range(item["nr_of_items_in_sockets"])
        ]
    return item


def parse_item_list(raw: bytes, list_byte_offset: int, version: int = 105,
                    constants: Optional[dict] = None) -> List[dict]:
    """Parses a 'JM' item list (the one located by d2s.items.find_items).
    Uses a ±byte resync heuristic for v105 items whose tails carry an extra
    alignment byte (observed on some magic rings)."""
    constants = constants or load_constants()
    bs = BitStream(bytearray(raw), list_byte_offset * 8)
    if bytes(bs.buf[bs.tell() // 8: bs.tell() // 8 + 2]) != b"JM":
        raise ValueError("Item list marker 'JM' not found")
    bs.seek(bs.tell() + 16)
    count = bs.read_bits(16)
    items = []
    p = bs.tell()

    def _valid(it: dict) -> bool:
        # Valid item: its type resolves to a name in the base tables (garbled
        # types produced by a mis-synced parse are not in the tables)
        if it.get("is_ear"):
            return True
        t = (it.get("type") or "").strip()
        details = _get_item_details(t, constants)
        return details is not None

    for _ in range(count):
        parsed = None
        for shift in (0, 8, -8, 16, 24, -16, 32):
            try:
                trial = BitStream(bytearray(raw), p + shift)
                it = parse_item(trial, version, constants)
                if _valid(it):
                    parsed = (it, trial.tell(), shift)
                    break
            except Exception:
                continue
        if not parsed:
            break
        it, p, shift = parsed
        items.append(it)
    return items


# ---------------------------------------------------------------------------
# naming / display

def describe_item(item: dict, constants: Optional[dict] = None) -> dict:
    constants = constants or load_constants()
    i18n = load_i18n()
    parts: List[str] = []
    if item.get("personalized_name"):
        parts.append(f"'{item['personalized_name']}'")
    q = item.get("quality")
    if q == 7 and "unique_id" in item:
        zh = i18n.get("uniques", {}).get(str(item["unique_id"]))
        parts.append(zh or _by_id(constants["unq_items"], item["unique_id"]).get("n", "?"))
    elif q == 5 and "set_id" in item:
        zh = i18n.get("sets", {}).get(str(item["set_id"]))
        parts.append(zh or _by_id(constants["set_items"], item["set_id"]).get("n", "?"))
    elif q in (6, 8):
        rn = constants.get("rare_names") or []
        n1 = rn[item["rare_name_id"]]["n"] if item.get("rare_name_id") and rn else ""
        n2 = rn[item["rare_name_id2"]]["n"] if item.get("rare_name_id2") and rn else ""
        parts.append(" ".join(x for x in (n1, n2) if x))
    base = item.get("base_name") or item.get("type") or "?"
    base_zh = _zh_item((item.get("type") or "").strip()) or _zh_item(base)
    if base_zh:
        base = base_zh
    if q == 4:  # magic: prefix + base + suffix
        pre = item.get("magic_prefix")
        suf = item.get("magic_suffix")
        aff = i18n.get("affixes", {})
        pre_en = constants["magic_prefixes"][pre]["n"] if pre and constants["magic_prefixes"] else None
        suf_en = constants["magic_suffixes"][suf]["n"] if suf and constants["magic_suffixes"] else None
        pre_n = aff.get(pre_en, pre_en) if pre_en else None
        suf_n = aff.get(suf_en, suf_en) if suf_en else None
        parts.append(" ".join(x for x in (pre_n, base, suf_n) if x))
    else:
        parts.append(base)
    if item.get("given_runeword"):
        rw = i18n.get("runewords", {}).get(str(item.get("runeword_id")))
        if not rw:
            rw = _by_id(constants["runewords"], item.get("runeword_id")).get("n", "runeword")
        parts.append(f"[{rw}]")
    title = " ".join(parts) if parts else "?"
    if item.get("ethereal"):
        title += " (eth)"
    if item.get("socketed") == 1:
        title += f" (sock {item.get('total_nr_of_sockets', '?')})"
    qname = QUALITY_NAMES.get(q) if q is not None else "Item"
    return {"title": title, "quality": qname}


def describe_magic_prop(prop: dict, constants: Optional[dict] = None) -> str:
    """Human-readable line for one magic property. Prefers the official zh-CN
    template from the generated table; falls back to the English template.
    %s params (skill names etc.) also prefer zh-CN when available."""
    constants = constants or load_constants()
    i18n = load_i18n()
    mp = constants["magical_properties"]
    params = [f["param"] for f in prop.get("fields", []) if "param" in f]
    values = [f["value"] for f in prop.get("fields", []) if "value" in f]
    template = i18n.get("stat_tpl", {}).get(str(prop["id"])) \
        or mp[prop["id"]].get("dP") or mp[prop["id"]].get("dN") or prop["name"]
    # stat 83 (item_addclassskills, descfunc 13 in game) picks a different
    # official string per class param; the constants table only registers the
    # first class (Amazon) template, so pick the official string for the
    # actual class param here.
    if prop["id"] == 83 and params:
        cls_tpl = i18n.get("class_skill_tpl", {}).get(str(params[0]))
        if cls_tpl:
            template = cls_tpl
    skills = constants.get("skills") or []
    skills_zh = i18n.get("skills", {})

    def _skill_name(v):
        # Prefer official zh-CN by skill id (covers mod-defined skills), then
        # by English name
        by_id = i18n.get("skills_by_id", {})
        if isinstance(v, int):
            z = by_id.get(str(v))
            if z:
                return z
            if 0 <= v < len(skills) and skills[v]:
                en = skills[v].get("n") or skills[v].get("s")
                return skills_zh.get(en) or en or f"Skill#{v}"
            return f"Skill#{v}"
        if isinstance(v, str):
            return skills_zh.get(v, v)
        return str(v)

    # chance-to-cast (e==2) / charged (e==3): the template param order is
    # special, reassemble values per the encoding rules
    sub = mp[prop["id"]]
    lead = prop.get("values") or []  # leading values unpacked from the param (cast/charges level)
    if sub.get("e") == 2 and lead:
        # template order: chance % (field value) ... level (lead) skill (param)
        values = values + [lead[0]]
    elif sub.get("e") == 3 and lead:
        # template order: level (lead) skill (param) cur/max charges
        ch = prop["fields"][0].get("charges") or {}
        values = [lead[0], ch.get("cur", 0), ch.get("max", 0)]

    out = []
    vi = pi = 0
    i = 0
    while i < len(template):
        ch = template[i]
        if ch == "%" and i + 1 < len(template):
            if template[i + 1] == "s":
                if pi < len(params):
                    v = params[pi]
                    pi += 1
                    out.append(_skill_name(v))
                # params exhausted: emit empty string (e.g. item_singleskill's
                # second %s = class name)
                i += 2
                continue
            if template[i + 1] == "d":
                v = values[vi] if vi < len(values) else 0
                if vi < len(values):
                    vi += 1
                out.append(str(v))
                i += 2
                continue
            if template[i + 1] == "+":
                v = values[vi] if vi < len(values) else 0
                if vi < len(values):
                    vi += 1
                out.append(("+" if v >= 0 else "") + str(v))
                i += 3  # skip %+d
                continue
        out.append(ch)
        i += 1
    return "".join(out).replace("%%", "%")
