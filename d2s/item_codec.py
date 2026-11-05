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

# 编码查找表: 字符 -> (位值, 位长) — 与上面树一致 (源自 dschu012/d2s items.js)
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
    """4 字符类型码 -> LSB-first 位序列"""
    bits = []
    for ch in t:
        v, l = HUFFMAN_LOOKUP[ch]
        for i in range(l):
            bits.append((v >> i) & 1)
    return bits

# 宝石阶链: gc碎裂 -> gf有瑕疵 -> gs普通 -> gl无瑕 -> gp完美 (末位=种类 v紫/r红/g绿/b蓝/y黄); 头骨 skc/skf/sks/skl/skz
# 宝石阶顺序 (按官方中文名前缀分组排序, 不依赖代码字母 — Infernal 的代码方案与经典版不同)
GEM_TIER_NAMES = ["碎裂的", "有瑕疵的", "普通", "无瑕的", "完美的"]

def gem_tiers(constants: Optional[dict] = None) -> dict:
    """宝石升级链: {当前代码: 下一阶代码}。
    按官方中文名识别阶与种类 (如 碎裂的紫宝石/有瑕疵的紫宝石/紫宝石/无瑕的紫宝石/完美的紫宝石),
    同名阶梯内按阶顺序链接。mod 改码方案不影响 (名称来自游戏字符串表)。
    无 i18n 表时回退英文官方名分组 (上游英文环境同样可用)。"""
    constants = constants or load_constants()
    i18n = load_i18n()
    items = i18n.get("items", {})
    groups = {}
    for key, zh in items.items():
        if key.startswith("en:") or len(key) != 3:
            continue
        if ("宝石" not in zh and "头骨" not in zh) or "神符" in zh or "珠宝" in zh:
            continue
        if zh.startswith("完美的"):
            tier, base = 4, zh[3:]
        elif zh.startswith("无瑕的"):
            tier, base = 3, zh[3:]
        elif zh.startswith("有瑕疵的"):
            tier, base = 1, zh[4:]
        elif zh.startswith("碎裂的"):
            tier, base = 0, zh[3:]
        else:
            tier, base = 2, zh
        groups.setdefault(base, []).append((tier, key, zh))
    chains = {}
    for base, lst in groups.items():
        lst.sort()
        for a, b in zip(lst, lst[1:]):
            chains[a[1]] = b[1]
    if chains:
        return chains

    # 英文兜底: 未生成 i18n 表时, 用 constants 里的官方英文名分组
    # (Chipped/Flawed/Flawless 前缀 + 裸基准名), 让宝石升阶在英文环境下同样可用
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
        # D2R 新版: 回复药水有"满度"数量字段, 经典表里没有 (实测 v105 存档验证)
        stack = c.setdefault("stackables", {})
        for t in ("rvs", "rvl"):
            stack.setdefault(t, {"n": "Rejuvenation Potion"})
        _CONSTANTS = c
    return _CONSTANTS


def load_i18n() -> dict:
    """官方简体中文显示映射 (单向: 仅用于显示, 不影响任何写回数据)。"""
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
        print(f"      props 起点 {bs.tell()}")
    while True:
        prop_start = bs.tell()
        id_ = bs.read_bits(9)
        if _dbg:
            print(f"      prop id={id_} @{bs.tell()-9}", end="")
        if id_ == 0x1FF:
            if _dbg:
                print(" -> 终止符")
            break
        if _dbg:
            print()
        if id_ >= len(mp_all):
            raise ValueError(f"Invalid stat id {id_} at bit {bs.tell() - 9}")
        prop_out = {"id": id_, "name": mp_all[id_]["s"], "fields": [],
                    "_start_bit": prop_start}  # id 读取前位置 (删除/插入用)
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
                field["value"] = v & 0xFF  # 展示当前充能次数 (只读)
            else:
                v -= sa
                field["value"] = v
                field["editable"] = not sp
            prop_out["fields"].append(field)
        prop_out["_end_bit"] = bs.tell()  # 该组 (np 全部部件) 读完位置
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


# 参数词缀白名单: param_kind -> UI/插入所需的参数语义
#   skill:     参数 = 技能id (如 item_singleskill +X 到某技能)
#   class:     参数 = 职业id (0..7, item_addclassskills)
#   tab_skill: 参数 = (技能页tab, 技能id), dF==14 打包 tab(3位)|skill(13位)<<3
#   cast:      参数 = (等级, 技能id), e==2 打包 level(6位)|skill(10位)<<6, 数值 = 概率%
#   charges:   参数 = (等级, 技能id), 数值 = (当前次数, 最大次数) 打包 cur|max<<8
_PARAM_PROPS = {
    83: "class",      # item_addclassskills
    97: "skill",      # item_nonclassskill
    107: "skill",     # item_singleskill
    151: "skill",     # item_aura
    188: "tab_skill",  # item_addskill_tab (dF==14)
    195: "cast", 196: "cast", 197: "cast", 198: "cast", 199: "cast", 201: "cast",
    204: "charges",   # item_charged_skill
}


def list_addable_props(constants: Optional[dict] = None) -> List[dict]:
    """可添加的词缀列表: 纯数值型 + 带参数型 (技能/职业/技能tab/触发施放/聚气)。
    返回 [{id, name, desc, sB, sA, min, max, param_kind, param_bits}] 按描述排序。
    desc 优先用官方简体中文模板 (i18n stat_tpl), 无中文时回退常量表英文 dP/dN。
    param_kind 为 None 表示纯数值词缀, 否则见 _PARAM_PROPS 注释。
    仍排除: np 多部件分组词缀、参数语义未支持的词缀 (state/montype/reanimate 等)。"""
    constants = constants or load_constants()
    i18n = load_i18n()
    stat_tpl = i18n.get("stat_tpl", {})
    # 参数语义绑定了具体参数值的官方模板 (如 stat 83 dP 硬编码亚马逊, stat 188 硬编码
    # 标枪和长矛页), 下拉列表统一改用中性文案避免误导; 插入后的表格显示仍按实际参数
    # 给出官方文案 (stat 83 见 describe_magic_prop)。
    neutral_desc = {83: "%+d 职业技能等级", 188: "%+d 技能页技能"}
    out = []
    for i, p in enumerate(constants["magical_properties"]):
        param_kind = _PARAM_PROPS.get(i)
        if not p or p.get("np"):
            continue
        if p.get("sP") and param_kind is None:
            continue  # 带参数但语义未支持的 (state/montype/reanimate/elemskill 等)
        if not p.get("sP") and p.get("e") in (1, 2, 3):
            continue
        sB = p.get("sB")
        if not sB or sB > 21:  # 过宽/异常的跳过
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
        if param_kind == "charges":  # 数值 = (当前, 最大) 次数, 各 8 位
            entry["min"], entry["max"] = 1, 255
        out.append(entry)
    out.sort(key=lambda x: (x["id"] > 100, x["desc"].lower()))
    return out


def _pack_param(sub: dict, param) -> Optional[int]:
    """按编码规则把参数打包成 sP 位原始值; 词缀无 sP 时返回 None。
    param: None / int (技能id、职业id 等原始参数) / 二元组:
      - dF==14: (tab, skill_id) -> tab | skill<<3
      - e in (2,3): (level, skill_id) -> level | skill<<6"""
    sp = sub.get("sP")
    if not sp:
        if param is not None:
            raise ValueError(f"{sub['s']} 无参数字段, 不应传入参数")
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
        raise ValueError(f"参数超出范围 0..{(1 << sp) - 1} (词缀 {sub['s']})")
    return p


def _pack_value(sub: dict, value) -> int:
    """显示值 -> 存储原始值 (加 sA 偏移)。e==3 聚气传 (当前次数, 最大次数),
    打包 = 当前+体 | 最大<<8 (与参考实现 items.js 一致)。"""
    sA = sub.get("sA", 0) or 0
    sB = sub.get("sB")
    if not sB:
        raise ValueError(f"词缀 {sub['s']} 无位宽定义, 无法添加")
    if sub.get("e") == 3:
        cur, mx = value
        cur, mx = int(cur), int(mx)
        if not (0 <= cur <= 255 and 0 <= mx <= 255):
            raise ValueError("充能次数超出范围 0..255")
        v = (cur + sA) | ((mx & 0xFF) << 8)
    else:
        v = int(value) + sA
    if not (0 <= v < (1 << sB)):
        raise ValueError(f"数值超出范围 {[-sA, (1 << sB) - 1 - sA]} (词缀 {sub['s']})")
    return v


def _encode_prop_bits(prop_id: int, fields_spec: list, constants: dict) -> List[int]:
    """把一条词缀编码为 LSB-first 位列表: id(9) + 每个部件的 param(sP)+value(sB)。"""
    mp = constants["magical_properties"]
    if not (0 <= prop_id < len(mp)) or not mp[prop_id]:
        raise ValueError(f"未知词缀 id: {prop_id}")
    sub0 = mp[prop_id]
    num = sub0.get("np") or 1  # np 分组: fields_spec 每个部件一组 (参数, 数值)
    if len(fields_spec) != num:
        raise ValueError(f"该词缀需要 {num} 组 (参数, 数值), 实际传入 {len(fields_spec)} 组")
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
    """词缀终止符之后、对齐补零之前的实际数据结束位 (含套装/符文之语属性表)。
    拼接词缀表时丢弃旧的对齐空位并按新长度重新规整, 避免残留杂散字节。"""
    end = item["_term_bitpos"] + 9  # 9 位终止符之后
    lists = list(item.get("set_attributes") or []) + [item.get("runeword_attributes")]
    for lst in lists:
        for p in lst or []:
            pe = p.get("_end_bit")
            if pe:
                end = max(end, pe)
    return min(end, item["_end_bit"])


def add_magic_prop_ex(raw: bytearray, item: dict, prop_id: int, fields_spec: list,
                      constants: Optional[dict] = None) -> None:
    """向物品词缀表插入一条任意词缀 (位流外科手术, add_magic_prop 的通用版):
      [前缀低位][原词缀位逐位保留][新词缀位][终止符及套装/符文属性位逐位保留][补齐字节][原尾部数据]
    fields_spec: [(param 或 None, value), ...] 按 sub-field 顺序, 编码规则见 _pack_param/_pack_value。
    插入后旧的对齐空位被丢弃并按新长度重新补零 (下一物品仍字节对齐, 无杂散字节)。
    之后调用方需重新解析/保存 (保存时自动修校验和)。"""
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
    """向物品词缀表插入一条纯数值词缀 (兼容入口, 内部转 add_magic_prop_ex)。
    位流布局: [原词缀位 逐位保留] + [新词缀位] + [9位终止符] + [补齐字节] + [原尾部数据]
    之后调用方需重新解析/保存 (保存时自动修校验和)。"""
    constants = constants or load_constants()
    sub = constants["magical_properties"][prop_id]
    if sub.get("sP") or sub.get("np") or sub.get("e") in (1, 2, 3):
        raise ValueError("该词缀带特殊编码, 暂不支持添加 (纯数值词缀之外请用 add_magic_prop_ex)")
    if not sub.get("sB"):
        raise ValueError("该词缀无位宽定义, 无法添加")
    add_magic_prop_ex(raw, item, prop_id, [(None, value)], constants)


def delete_magic_prop(raw: bytearray, item: dict, prop: dict,
                      constants: Optional[dict] = None) -> None:
    """从物品词缀表删除一条词缀 (np 组整体删除; 位流外科手术, 与插入互为镜像):
      [前缀低位][props_start..prop._start_bit 原位][prop._end_bit..终止符/套装属性 原位]
      + [补齐字节] + [原尾部数据]
    旧的对齐空位被丢弃并按新长度重新补零 (删除同批插入的词缀可精确还原字节)。
    之后调用方需重新解析/保存 (保存时自动修校验和)。"""
    start = item["_props_start_bit"]
    term = item["_term_bitpos"]
    data_end = _trailing_prop_bits_end(item)
    ps = prop.get("_start_bit")
    pe = prop.get("_end_bit")
    if ps is None or pe is None:
        raise ValueError("该词缀缺少位位置信息, 请重新加载存档后再试")
    if not (start <= ps < pe <= term):
        raise ValueError("词缀位位置异常 (可能属于套装/符文之语属性表), 拒绝删除")

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
    """更换简单物品的类型代码 (变基, 如宝石升阶 gcv -> gpv, 或符文 r07 -> r33)。
    位流手术: 替换类型码位段(霍夫曼变长), 后续位整体平移,
    调用方需重新解析/保存。仅支持简单物品 (药水/宝石/卷轴等)。

    span_end: 物品在文件中实际占用的位跨度末尾 (字节对齐)。D2R 会给部分简单
    物品 (宝石/符文等) 在解析字段之后追加一个全零的对齐/堆叠字节, 表现为
    下一物品的 _start_bit 比本物品 _end_bit 靠后 8 位。传入 span_end (= 下一
    物品的 _start_bit) 时, 类型码位长变化在物品跨度内消化:
      - 变长 (delta>0): 用 span 末尾的全零字节抵扣 (非全零则拒绝),
        物品总跨度不变, 其余字节完全不动 — 变长转换对游戏内安全;
      - 变短/等长 (delta<=0): span 末尾补零对齐, 跨度不变。
    不传 (None) 时保持旧行为: 以 item['_end_bit'] 为界平移 (等长转换如
    宝石升阶不受影响, 变长时文件尾部字节会平移, 供既有调用方兼容)。"""
    if item.get("simple_item") != 1:
        raise ValueError("仅支持简单物品 (宝石/药水/卷轴等) 的类型更换")
    tb = item.get("_type_bits")
    if not tb:
        raise ValueError("该物品缺少类型位信息, 请重新加载存档")
    if len(new_type) != 4:
        new_type = (new_type + "    ")[:4]
    for ch in new_type.strip() or " ":
        if ch not in HUFFMAN_LOOKUP:
            raise ValueError(f"类型码含无法编码的字符: {ch!r}")

    t_start, t_end = tb
    new_code_bits = encode_type_code(new_type)
    delta = len(new_code_bits) - (t_end - t_start)
    end = item["_end_bit"]
    if span_end is None:
        span_end = end
    if not (t_end <= end <= span_end <= len(raw) * 8) or span_end % 8:
        raise ValueError("物品位跨度信息异常, 请重新加载存档后再试")
    if delta > 0:
        trim = 8 * ((delta + 7) // 8)  # 需要抵扣的全零字节数
        if span_end - end < trim:
            raise ValueError(
                "该物品尾部没有足够的全零填充字节来消化类型码变长, "
                "无法安全转换 (把物品移动位置/重新加载存档后再试)")
        for p in range(span_end - trim, span_end):
            if (raw[p // 8] >> (p % 8)) & 1:
                raise ValueError("该物品尾部填充字节非全零, 为避免损坏物品已拒绝转换")
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
        raise ValueError("类型码转换后无法对齐回原物品跨度 (已中止, 未写入)")
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
    # 简单物品若带数量(回复药满度等), 数量字段紧跟其后
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
        # 合法物品: 类型能在基础表里找到名字 (乱码类型解析出的 type 不在表里)
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
    qname = QUALITY_NAMES.get(q) if q is not None else "物品"
    return {"title": title, "quality": qname}


def describe_magic_prop(prop: dict, constants: Optional[dict] = None) -> str:
    """Human-readable line for one magic property. 优先使用官方简体中文模板,
    找不到时回退英文模板。%s 参数 (技能名等) 同样优先中文。"""
    constants = constants or load_constants()
    i18n = load_i18n()
    mp = constants["magical_properties"]
    params = [f["param"] for f in prop.get("fields", []) if "param" in f]
    values = [f["value"] for f in prop.get("fields", []) if "value" in f]
    template = i18n.get("stat_tpl", {}).get(str(prop["id"])) \
        or mp[prop["id"]].get("dP") or mp[prop["id"]].get("dN") or prop["name"]
    # stat 83 (item_addclassskills, 游戏 descfunc 13) 按职业参数选用不同官方串,
    # 常量表只登记了第一个职业 (亚马逊) 的模板; 这里按参数取对应职业的官方文案。
    if prop["id"] == 83 and params:
        cls_tpl = i18n.get("class_skill_tpl", {}).get(str(params[0]))
        if cls_tpl:
            template = cls_tpl
    skills = constants.get("skills") or []
    skills_zh = i18n.get("skills", {})

    def _skill_name(v):
        # 优先按技能 id 查官方中文 (覆盖 mod 自定义技能), 再按英文名
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

    # 触发施放 (e==2) / 聚气 (e==3): 模板参数顺序特殊, 按编码规则重组
    sub = mp[prop["id"]]
    lead = prop.get("values") or []  # 参数解包出的前置值 (触发/聚气的等级)
    if sub.get("e") == 2 and lead:
        # 模板顺序: 概率%(字段值) ... 等级(lead) 技能(参数)
        values = values + [lead[0]]
    elif sub.get("e") == 3 and lead:
        # 模板顺序: 等级(lead) 技能(参数) 当前/最大次数
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
                # 参数用尽时输出空串 (如 item_singleskill 的第二 %s = 职业名)
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
