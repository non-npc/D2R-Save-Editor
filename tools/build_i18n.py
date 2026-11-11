"""Build the optional zh-CN display table d2s/data/i18n_zh.json from the
official game string tables extracted by tools/casc_extract.py.

This is the generator for the editor's runtime-loaded language table (the
regular localization system): the output file is NOT committed to the repo;
users generate it from their own game install. All mappings are one-way and
display-only - they never affect any data written back to a save. Without the
table the editor runs fully in English.
"""
import json
import os

EX = os.path.join(os.path.dirname(__file__), "extracted")
OUT = os.path.join(os.path.dirname(__file__), "..", "d2s", "data", "i18n_zh.json")


def load(name):
    return json.load(open(os.path.join(EX, name), encoding="utf-8-sig"))


def zh(e):
    return e.get("zhCN") or e.get("zhTW") or ""


# 1. Item names: Key (type code) -> zh-CN. "en:<English name>" aliases are
#    added as a fallback lookup path.
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
        items.setdefault("en:" + en, z)  # fallback lookup by English name
    # Affix-shaped names: "of ..." suffixes / single-word prefixes; also
    # indexed under the English name for the affix display mapping
    if en and (en.startswith("of ") or (en.isalpha() and len(en) <= 12 and " " not in en)):
        affixes.setdefault(en, z)

# 1.5 Rune names, manual supplement RUNE_NAMES_ZH. In saves, runes use the
#     type codes r01..r33 (runes #1-33), but item-names.json does not register
#     those keys - the string table attaches rune names to separate rune
#     entries. So the official-style zh names (El..Zod order) are supplemented
#     by hand here. Part of the generated language table; one-way mapping:
#     the zh name is display-only, saves are always written with the type
#     code ('r07' etc.), never Chinese.
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

# 2. Skill names: English name -> zh-CN, plus skills.txt row id -> zh-CN.
#    Note: the id in skills.json is a localization row number, not the game
#    skill id; the game skill id = the skills.txt row number, which is mapped
#    to zh-CN through its English name in skills.json.
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
            _sid = int(_cols[1])  # column 2 = game skill id (0..428)
        except ValueError:
            continue
        _en = _cols[_i_skill].strip()
        skills_by_id[str(_sid)] = skills_zh.get(_en) or _en

# 3. Stat description templates: descstrpos key -> zh-CN
mods = load("item-modifiers.json")
mods_zh = {}
for e in mods:
    if isinstance(e, dict) and e.get("Key") and zh(e):
        mods_zh[e["Key"]] = zh(e)

# 4. stat_id -> zh-CN template (from itemstatcost.txt descstrpos/descstrneg)
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

# Manual template overrides MANUAL_OVERRIDES: {stat_id: zh-CN template}.
# Only needed when the official string table (item-modifiers.json) has no
# usable zhCN for a stat's descstrpos/descstrneg. Unconditionally written into
# stat_tpl on rebuild. Translation rule: semantics must be exact (check the
# English dP/dN, the enUS description and the stat name); when in doubt, leave
# it untranslated (keep English display) rather than mislead the user; keep
# %s placeholder syntax (skill names etc.) as-is. These zh templates are part
# of the generated language table.
MANUAL_OVERRIDES = {
    160: "投掷最大伤害 %+d",  # item_throw_maxdamage: no desc key in itemstatcost
    23: "最小伤害 %+d",       # secondary_mindamage (matches official ModStr1g, fallback)
    24: "最大伤害 %+d",       # secondary_maxdamage (matches official ModStr1f, fallback)
}
for _mid, _mtpl in MANUAL_OVERRIDES.items():
    stat_tpl[str(_mid)] = _mtpl

# 5. Per-class skill level templates (stat 83 item_addclassskills, descfunc 13):
#    the game picks a different official string per class param, but
#    itemstatcost only registers ModStr3a (Amazon); the other class strings
#    (ModStr3b-e / ModStre8a-b) are extracted by matching their enUS text.
#    (D2R official zh-CN names; class-key rows may carry zh only)
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
    print(f"WARNING: missing class skill templates for: {missing_cls} "
          "(stat 83 display will fall back to the Amazon template)")

# 6. Uniques / sets / runewords: saves store row ids -> map to zh via the
#    txt tables' code/name columns
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
    i_name = idx.get("index")  # index column = unique/set name string
    i_code = idx.get("code")
    for i, r in enumerate(rows):
        if i_name is None or i_name >= len(r):
            continue
        name_str = r[i_name].strip()
        z = items.get(name_str) or items.get("en:" + name_str)
        if not z and i_code is not None and i_code < len(r):
            z = items.get(r[i_code].strip())  # fallback: base item code
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

# 7. UI labels: stable English key -> zh-CN text for every visible UI string in
#    app/main.py (tabs, menus, buttons, group titles, table headers, tooltips,
#    dialogs). This is the "ui" section of the generated language table:
#    app/main.py renders English by default and swaps in these values at
#    runtime via its tr() helper when the table exists. Keeping the zh strings
#    here (not in the code) is what makes the localization regular - the
#    codebase itself stays English-only.
UI_LABELS_ZH = {
    # tabs
    "tab_overview": "概览",
    "tab_stats": "属性",
    "tab_skills": "技能",
    "tab_quests": "任务",
    "tab_waypoints": "传送点",
    "tab_items": "物品 (编辑)",
    "tab_diagnostics": "诊断",
    # menus / actions
    "menu_file": "文件",
    "menu_settings": "设置",
    "menu_help": "帮助",
    "act_open_save": "打开存档…",
    "act_generate_character": "生成新角色…",
    "act_save": "保存",
    "act_save_as": "另存为…",
    "act_exit": "退出",
    "act_settings": "设置…",
    "act_about": "关于…",
    # overview tab
    "lbl_signature": "签名",
    "lbl_version": "版本",
    "lbl_file_size": "文件大小",
    "lbl_checksum_stored": "校验和(存储)",
    "lbl_checksum_valid": "校验和有效?",
    "lbl_name": "名字",
    "lbl_class": "职业",
    "lbl_level": "等级",
    "lbl_legacy_flags": "旧版标志位",
    "lbl_note": "备注",
    "overview_note_empty": "请打开一个 .d2s 存档文件开始使用。",
    # stats tab
    "group_core_stats": "基础属性",
    "group_life_mana": "生命 / 法力 / 精力",
    "group_level_exp_gold": "等级 / 经验 / 金币",
    "stat_0": "力量", "stat_1": "能量", "stat_2": "敏捷", "stat_3": "体力",
    "stat_4": "未用属性点", "stat_5": "未用技能点",
    "stat_6": "当前生命", "stat_7": "最大生命",
    "stat_8": "当前法力", "stat_9": "最大法力",
    "stat_10": "当前精力", "stat_11": "最大精力",
    "stat_12": "等级", "stat_13": "经验", "stat_14": "金币", "stat_15": "仓库金币",
    # items tab: groups / labels / headers
    "group_equipped": "身上装备",
    "group_inventory": "背包",
    "group_raw_list": "物品列表 (原始解析)",
    "group_item_edit": "物品列表 / 词缀数值修改",
    "lbl_select_item": "选择物品:",
    "tip_click_cells": "提示: 点击上方「身上装备 / 背包」格子可直接选中该物品并编辑词缀。",
    "col_affix": "词缀属性",
    "col_current": "当前值",
    "col_new": "修改为",
    "col_status": "状态",
    "col_action": "操作",
    "btn_apply_affixes": "应用词缀数值修改",
    "btn_add_affix": "➕ 添加词缀",
    "btn_gem_upgrade": "⬆ 宝石升一阶",
    "btn_gem_max": "⬆⬆ 宝石升到完美",
    "lbl_rune": "符文:",
    "rune_placeholder": "选择目标符文…",
    "btn_rune_convert": "转换为此符文",
    "status_editable": "可修改",
    "status_readonly": "只读",
    "status_special_readonly": "(特殊编码, 只读)",
    "btn_delete": "删除",
    "tooltip_delete_affix": "从词缀表删除该词缀 (np 分组整组删除)",
    "hdr_defense": "防御 (Defense)",
    "hdr_max_durability": "耐久上限 (Max Durability)",
    "hdr_durability": "当前耐久 (Durability)",
    "hdr_quantity": "数量 (Quantity)",
    # gem upgrade / rune conversion dialogs
    "dlg_title_info": "提示",
    "msg_not_gem": "选中的物品不是可升级的宝石。",
    "dlg_title_upgrade_failed": "升阶失败",
    "dlg_title_upgrade_ok": "升阶成功",
    "msg_upgrade_ok": "宝石已升为「{title}」\nCtrl+S 保存到文件 (自动备份 .bak)。",
    "msg_not_rune": "选中的物品不是符文。",
    "msg_no_rune_target": "请先在下拉框选择目标符文。",
    "dlg_title_convert_failed": "转换失败",
    "dlg_title_convert_ok": "转换成功",
    "msg_convert_ok": "物品已转换为「{title}」\nCtrl+S 保存到文件 (自动备份 .bak)。",
    "dlg_title_parse_warning": "物品解析",
    "msg_parse_failed": "完整物品解析失败（不影响其他功能）:\n{error}",
    # add-affix dialog
    "dlg_title_add_affix": "添加词缀 → {title}",
    "lbl_target_item": "目标物品: {title}",
    "lbl_affix": "词缀:",
    "param_hint": "需要参数",
    "lbl_skill": "技能:",
    "lbl_skill_level": "技能等级:",
    "lbl_skill_tab": "技能页 (0-7):",
    "lbl_cur_charges": "当前次数:",
    "lbl_max_charges": "最大次数:",
    "lbl_value": "数值:",
    "lbl_chance": "概率 (%):",
    "note_add_affix": "提示: 带技能词缀支持输入关键字搜索; 词缀将插入到该物品的词缀表末尾。\n保存时原文件自动备份为 .bak。",
    "msg_select_item_first": "请先在上方选择一件物品。",
    "dlg_title_add_failed": "添加失败",
    "dlg_title_add_ok": "添加成功",
    "msg_add_ok": "已为「{title}」添加: {desc}\nCtrl+S 保存到文件 (自动备份 .bak)。",
    # delete-affix dialog
    "dlg_title_delete_affix": "删除词缀",
    "msg_delete_confirm": "确定从该物品删除这条词缀?\n\n{desc}",
    "dlg_title_delete_failed": "删除失败",
    "dlg_title_delete_ok": "删除成功",
    "msg_delete_ok": "已删除词缀: {desc}\nCtrl+S 保存到文件 (自动备份 .bak)。",
    # affix value editing
    "dlg_title_applied": "已应用",
    "msg_apply_ok": "已修改 {count} 处词缀数值（写入内存，Ctrl+S 保存到文件）。\n保存时原文件会自动备份为 .bak。",
    "dlg_title_no_changes": "无改动",
    "msg_no_changes": "没有需要应用的修改。",
    "dlg_title_edit_failed": "修改失败",
    # parametric prop kinds (affix dropdown hints)
    "param_kind_skill": "选择技能",
    "param_kind_class": "选择职业",
    "param_kind_tab_skill": "技能页+技能",
    "param_kind_cast": "概率+等级+技能",
    "param_kind_charges": "等级+技能+次数",
    # class names (D2R official zh-CN translations)
    "class_0": "亚马逊", "class_1": "巫师", "class_2": "死灵法师",
    "class_3": "圣骑士", "class_4": "野蛮人", "class_5": "德鲁伊", "class_6": "猎法者",
    # neutral dropdown templates for parametric stats whose official strings
    # hardcode the first class/tab (English fallbacks live in item_codec)
    "prop_neutral_83": "%+d 职业技能等级",
    "prop_neutral_188": "%+d 技能页技能",
}

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
    "ui": UI_LABELS_ZH,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print(f"i18n_zh.json: items {len(items)} | affixes {len(affixes)} | skills {len(skills_zh)} "
      f"| stat templates {len(stat_tpl)} | ui labels {len(UI_LABELS_ZH)}")
print(f"sample: leather armor = {items.get('lea')!r} | ring = {items.get('rin')!r} "
      f"| stat 7 template = {stat_tpl.get('7')!r}")
