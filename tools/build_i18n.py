"""从游戏提取的官方字符串表构建编辑器汉化映射 d2s/data/i18n_zh.json。
单向映射: 仅用于显示, 不影响任何写回存档的数据。"""
import json
import os

EX = os.path.join(os.path.dirname(__file__), "extracted")
OUT = os.path.join(os.path.dirname(__file__), "..", "d2s", "data", "i18n_zh.json")


def load(name):
    return json.load(open(os.path.join(EX, name), encoding="utf-8-sig"))


def zh(e):
    return e.get("zhCN") or e.get("zhTW") or ""


# 1. 物品名: Key(类型代码) -> 中文
item_names = load("item-names.json")
items = {}
affixes = {}
for e in item_names:
    if not isinstance(e, dict) or not e.get("Key"):
        continue
    z = zh(e)
    if not z:
        continue
    items[e["Key"]] = z
    en = e.get("enUS")
    if en and en not in items:
        items.setdefault("en:" + en, z)  # 英文名兜底查找
    # 词缀名特征: of 开头的后缀 / 纯前缀词 — 同时挂到英文名映射
    if en and (en.startswith("of ") or (en.isalpha() and len(en) <= 12 and " " not in en)):
        affixes.setdefault(en, z)

# 1.5 符文名手动补表 RUNE_NAMES_ZH: 存档里符文的类型代码是 r01..r33 (1-33号),
#     游戏字符串表的符文名挂在独立的 rune 名字上, item-names.json 未按 r01..r33
#     登记 Key, 故在此手动补充官方风格译名 (El..Zod 顺序)。
#     单向映射: 中文名仅用于显示, 写回存档的仍是类型代码 ('r07' 等), 绝不写中文。
RUNE_NAMES_ZH = {
    "r01": "艾尔符文",    # El
    "r02": "艾德符文",    # Eld
    "r03": "特尔符文",    # Tir
    "r04": "尼夫符文",    # Nef
    "r05": "爱斯符文",    # Eth
    "r06": "伊司符文",    # Ith
    "r07": "塔尔符文",    # Tal
    "r08": "拉尔符文",    # Ral
    "r09": "欧特符文",    # Ort
    "r10": "书尔符文",    # Thul
    "r11": "安姆符文",    # Amn
    "r12": "索尔符文",    # Sol
    "r13": "夏符文",      # Shael
    "r14": "多尔符文",    # Dol
    "r15": "海尔符文",    # Hel
    "r16": "艾欧符文",    # Io
    "r17": "卢姆符文",    # Lum
    "r18": "科符文",      # Ko
    "r19": "法尔符文",    # Fal
    "r20": "蓝姆符文",    # Lem
    "r21": "普尔符文",    # Pul
    "r22": "乌姆符文",    # Um
    "r23": "马尔符文",    # Mal
    "r24": "伊斯特符文",  # Ist
    "r25": "古尔符文",    # Gul
    "r26": "维斯特符文",  # Vex
    "r27": "欧姆符文",    # Ohm
    "r28": "罗符文",      # Lo
    "r29": "瑟尔符文",    # Sur
    "r30": "贝符文",      # Ber
    "r31": "乔符文",      # Jah
    "r32": "查姆符文",    # Cham
    "r33": "萨德符文",    # Zod
}
items.update(RUNE_NAMES_ZH)

# 2. 技能名: 英文名 -> 中文 + skills.txt 行号(id) -> 中文
#    注意: skills.json 的 id 是本地化行号, 不是游戏技能 id;
#    游戏技能 id = skills.txt 的行号, 经其英文名在 skills.json 里查中文。
skills = load("skills.json")
skills_zh = {}
skills_by_id = {}
for e in skills:
    if isinstance(e, dict) and e.get("enUS") and zh(e):
        skills_zh[e["enUS"]] = zh(e)

_sk_idx, _sk_rows = None, []
_sp = os.path.join(EX, "skills.txt")
if os.path.exists(_sp):
    _lines = open(_sp, encoding="utf-8", errors="replace").read().split("\n")
    _hdr = _lines[0].split("\t")
    _i_skill = _hdr.index("skill") if "skill" in _hdr else 1
    for _ln in _lines[1:]:
        _cols = _ln.split("\t")
        if len(_cols) <= max(_i_skill, 1):
            continue
        try:
            _sid = int(_cols[1])  # 第2列 = 游戏技能 id (0..428)
        except ValueError:
            continue
        _en = _cols[_i_skill].strip()
        skills_by_id[str(_sid)] = skills_zh.get(_en) or _en

# 3. 属性描述模板: descstrpos 键 -> 中文
mods = load("item-modifiers.json")
mods_zh = {}
for e in mods:
    if isinstance(e, dict) and e.get("Key") and zh(e):
        mods_zh[e["Key"]] = zh(e)

# 4. stat_id -> 中文模板 (来自 itemstatcost.txt 的 descstrpos/descstrneg)
lines = open(os.path.join(EX, "itemstatcost.txt"), encoding="utf-8", errors="replace").read().split("\n")
hdr = lines[0].split("\t")
idx = {h: i for i, h in enumerate(hdr)}
i_id, i_pos, i_neg = idx["*ID"], idx["descstrpos"], idx["descstrneg"]
stat_tpl = {}
for ln in lines[1:]:
    cols = ln.split("\t")
    if len(cols) <= i_pos:
        continue
    try:
        sid = int(cols[i_id])
    except ValueError:
        continue
    key = cols[i_pos].strip() or cols[i_neg].strip()
    if key and key in mods_zh:
        stat_tpl[str(sid)] = mods_zh[key]

# 手动补模板 MANUAL_OVERRIDES: {stat_id: 中文模板}。
# 仅当官方字符串表 (item-modifiers.json) 对该属性的 descstrpos/descstrneg 没有
# 可用 zhCN 时才需要在此补写; 重建时无条件覆盖写入 stat_tpl。
# 翻译原则: 语义必须准确 (参照英文 dP/dN、enUS 描述与属性名), 拿不准的宁可不翻
# (保留英文显示), 绝不误导用户; %s 参数占位 (技能名等) 保持 %s。
MANUAL_OVERRIDES = {
    160: "投掷最大伤害 %+d",  # item_throw_maxdamage: itemstatcost 无描述键
    23: "最小伤害 %+d",       # secondary_mindamage (与官方 ModStr1g 一致, 兜底)
    24: "最大伤害 %+d",       # secondary_maxdamage (与官方 ModStr1f 一致, 兜底)
}
for _mid, _mtpl in MANUAL_OVERRIDES.items():
    stat_tpl[str(_mid)] = _mtpl

# 5. 职业技能等级模板 (stat 83 item_addclassskills, descfunc 13):
#    游戏按职业参数选择不同官方串, itemstatcost 只登记了 ModStr3a (亚马逊),
#    其余职业串 (ModStr3b-e / ModStre8a-b) 按 enUS 匹配提取官方 zhCN。
#    注意官方译名: Sorceress=巫师, Assassin=猎法者 (D2R 简中官方, 非旧译 女法师/刺客)。
CLASS_EN = {0: "Amazon", 1: "Sorceress", 2: "Necromancer", 3: "Paladin",
            4: "Barbarian", 5: "Druid", 6: "Assassin"}
class_skill_tpl = {}
for _cid, _cen in CLASS_EN.items():
    _want = f"%+d to {_cen} Skill Levels"
    _z = ""
    for _e in mods:
        if isinstance(_e, dict) and _e.get("enUS") == _want and zh(_e):
            _z = zh(_e)
            break
    if _z:
        class_skill_tpl[str(_cid)] = _z
missing_cls = [CLASS_EN[c] for c in CLASS_EN if str(c) not in class_skill_tpl]
if missing_cls:
    print(f"警告: 职业技能等级模板缺失: {missing_cls} (stat 83 显示将回退亚马逊模板)")

# 6. 暗金/套装/符文之语: 存档里存的是行号 -> 经 txt 的 code/名称 转中文
def txt_rows(name):
    p = os.path.join(EX, name)
    if not os.path.exists(p):
        return None, []
    lines = open(p, encoding="utf-8", errors="replace").read().split("\n")
    hdr = lines[0].split("\t")
    idx = {h: i for i, h in enumerate(hdr)}
    rows = []
    for ln in lines[1:]:
        cols = ln.split("\t")
        if len(cols) > 3:
            rows.append(cols)
    return idx, rows


uniques, sets_zh, runewords_zh = {}, {}, {}
for _tbl, _out in (("uniqueitems.txt", uniques), ("setitems.txt", sets_zh)):
    idx, rows = txt_rows(_tbl)
    if not idx:
        continue
    i_name = idx.get("index")  # index 列 = 暗金/套装的名称字符串
    i_code = idx.get("code")
    for i, r in enumerate(rows):
        if i_name is None or i_name >= len(r):
            continue
        name_str = r[i_name].strip()
        z = items.get(name_str) or items.get("en:" + name_str)
        if not z and i_code is not None and i_code < len(r):
            z = items.get(r[i_code].strip())  # 兜底: 用基础物品代码
        if z:
            uniques_or_sets = _out
            uniques_or_sets[str(i)] = z
idx, rows = txt_rows("runes.txt")
if idx and "name" in idx:
    for i, r in enumerate(rows):
        try:
            en = r[idx["name"]].strip()
            z = items.get("en:" + en) or skills_zh.get(en)
            runewords_zh[str(i)] = z or en
        except Exception:
            pass

out = {
    "items": items,
    "affixes": affixes,
    "skills": skills_zh,
    "skills_by_id": skills_by_id,
    "stat_tpl": stat_tpl,
    "class_skill_tpl": class_skill_tpl,
    "uniques": uniques,
    "sets": sets_zh,
    "runewords": runewords_zh,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print(f"i18n_zh.json: 物品名 {len(items)} | 词缀名 {len(affixes)} | 技能 {len(skills_zh)} | 属性模板 {len(stat_tpl)}")
print("样例: 皮甲 =", items.get("lea"), "| 戒指 =", items.get("rin"), "| id7 模板 =", stat_tpl.get("7"))
