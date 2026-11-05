"""添加词缀汉化自检 (tests/test_affix_i18n.py)。

1) list_addable_props 的 170 条下拉文案全部为中文 (官方 zhCN 模板 / 标注的中性文案);
2) 每条词缀 插入→重解析→describe_magic_prop 显示 同样为中文, 数值往返一致;
3) stat 83 职业技能等级按职业参数显示对应官方文案 (含 巫师/猎法者);
4) 汉化仅作用于显示: 插入后删除可逐字节还原位流 (写回数据不受影响)。
全部操作在 sync/Amenda.d2s 的临时副本上进行, 绝不触碰真实存档。
运行: python tests/test_affix_i18n.py
"""
import os
import re
import shutil
import sys
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _save_source import ensure_test_save, test_save_path
SRC_SAVE = ensure_test_save()

from d2s.io import load_d2s
from d2s.item_codec import (
    parse_item_list, describe_magic_prop, list_addable_props,
    add_magic_prop_ex, delete_magic_prop,
)
from app.main import affix_fields_spec

_PASS = 0


def ok(cond, msg: str) -> None:
    global _PASS
    assert cond, f"断言失败: {msg}"
    _PASS += 1
    print(f"  [通过] {msg}")


def make_tmp_save(tag: str):
    """复制存档到临时目录并加载 (测试完由调用方清理)。"""
    tmp = tempfile.mkdtemp(prefix=f"d2r_i18n_{tag}_")
    dst = os.path.join(tmp, "Amenda.d2s")
    shutil.copy2(SRC_SAVE, dst)
    return load_d2s(dst), tmp


def reparse(save) -> list:
    return parse_item_list(bytes(save.raw), save.items.offset, version=save.header.version)


def get_helm(items):
    """身上槽1头盔 (插入目标), 与 test_affix_ops 同一定位。"""
    for it in items:
        if (it.get("location_id") == 1 and it.get("equipped_id") == 1
                and it["type"] == "hlm"):
            return it
    return None


_PH = re.compile(r"%\+?d|%s|%%")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_EN = re.compile(r"[A-Za-z]")


def is_zh_desc(text: str) -> bool:
    """中文文案: 含 CJK, 且去掉 %d/%s/%% 占位后不含拉丁字母。"""
    return bool(_CJK.search(text)) and not _EN.search(_PH.sub("", text))


def test_dropdown_zh():
    print("== 下拉列表: 170 条可添加词缀文案全部中文 ==")
    props = list_addable_props()
    ok(len(props) == 170, f"可添加词缀 170 条 (实际 {len(props)})")
    bad = [(p["id"], p["name"], p["desc"]) for p in props if not is_zh_desc(p["desc"])]
    ok(not bad, f"170 条下拉文案全部为中文 (残留英文: {bad})")
    # 中性参数文案: stat 83 / 188 不再显示写死第一个参数值的官方模板
    d83 = next(p["desc"] for p in props if p["id"] == 83)
    ok("职业" in d83, f"stat 83 下拉文案为中性描述: {d83!r}")
    d188 = next(p["desc"] for p in props if p["id"] == 188)
    ok("技能页" in d188, f"stat 188 下拉文案为中性描述: {d188!r}")


def test_insert_display_roundtrip():
    print("== 插入冒烟: 170 条逐条 插入→重解析→表格显示 ==")
    save, tmp = make_tmp_save("insert")
    try:
        items = reparse(save)
        helm = get_helm(items)
        ok(helm is not None, "找到身上槽1头盔 (插入目标)")
        n_orig = len(helm["magic_attributes"])
        props = list_addable_props()
        bad_desc, bad_id, bad_val = [], [], []
        for p in props:
            # 数值夹取到该词缀合法区间 (个别词缀如 item_damagetargetac 为偏移编码, 区间为负)
            v = max(p["min"], min(7, p["max"]))
            add_magic_prop_ex(save.raw, helm, p["id"],
                              affix_fields_spec(p, value=v, skill_id=36, tab=0,
                                                class_id=1, level=2, cur=3, mx=4))
            items = reparse(save)  # 插入后重新解析 (真实 UI 路径)
            helm = get_helm(items)
            new = helm["magic_attributes"][-1]
            if new["id"] != p["id"]:
                bad_id.append((p["id"], new["id"]))
                continue
            desc = describe_magic_prop(new)
            if not is_zh_desc(desc) or "Skill#" in desc:
                bad_desc.append((p["id"], desc))
            if p["param_kind"] is None and new["fields"][0]["value"] != v:
                bad_val.append((p["id"], v, new["fields"][0]["value"]))
        ok(not bad_id, f"170 条插入后重解析 id 一致 (异常: {bad_id})")
        ok(not bad_val, f"纯数值词缀插入后数值 7 往返一致 (异常: {bad_val})")
        ok(not bad_desc, f"插入后表格显示全部中文 (异常: {bad_desc})")
        ok(len(helm["magic_attributes"]) == n_orig + len(props),
           f"头盔词缀数 = 原有 {n_orig} + 新插入 {len(props)} (实际 {len(helm['magic_attributes'])})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_delete_byte_restore():
    print("== 位流安全: 插入一条词缀再删除, 文件逐字节还原 (汉化不影响写回) ==")
    save, tmp = make_tmp_save("restore")
    try:
        items = reparse(save)
        helm = get_helm(items)
        raw_before = bytes(save.raw)
        p7 = next(p for p in list_addable_props() if p["id"] == 7)  # +7 生命
        add_magic_prop_ex(save.raw, helm, 7, affix_fields_spec(p7, value=7))
        items = reparse(save)
        helm = get_helm(items)
        ok(helm["magic_attributes"][-1]["id"] == 7, "插入 +7 生命 (id=7) 成功")
        delete_magic_prop(save.raw, helm, helm["magic_attributes"][-1])
        ok(bytes(save.raw) == raw_before, "删除刚插入的词缀后文件逐字节还原")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_stat83_class_templates():
    print("== stat 83 职业技能等级: 按职业参数显示官方文案 ==")
    expect = {0: "亚马逊", 1: "巫师", 2: "死灵法师", 3: "圣骑士",
              4: "野蛮人", 5: "德鲁伊", 6: "猎法者"}
    bad = []
    for cls, name in expect.items():
        prop = {"id": 83, "name": "item_addclassskills",
                "fields": [{"param": cls, "value": 3}]}
        desc = describe_magic_prop(prop)
        if name not in desc or not is_zh_desc(desc):
            bad.append((cls, desc))
    ok(not bad, f"7 个职业分别显示对应官方文案 (异常: {bad})")


def test_i18n_data_integrity():
    print("== i18n 数据完整性 ==")
    from d2s.item_codec import load_i18n
    i18n = load_i18n()
    stat_tpl = i18n.get("stat_tpl", {})
    cls_tpl = i18n.get("class_skill_tpl", {})
    props = list_addable_props()
    missing = [p["id"] for p in props if str(p["id"]) not in stat_tpl]
    ok(not missing, f"170 条可添加词缀均有中文模板 (缺失: {missing})")
    ok(sorted(cls_tpl, key=int) == [str(i) for i in range(7)],
       f"class_skill_tpl 覆盖 7 个职业 (实际 {sorted(cls_tpl, key=int)})")
    ok(len(stat_tpl) >= 221, f"stat_tpl 共 {len(stat_tpl)} 条 (不少于原有 221)")


if __name__ == "__main__":
    test_i18n_data_integrity()
    test_dropdown_zh()
    test_insert_display_roundtrip()
    test_stat83_class_templates()
    test_add_delete_byte_restore()
    print(f"\n添加词缀汉化全部通过: {_PASS} 条断言。")
