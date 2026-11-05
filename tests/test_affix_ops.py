"""词缀删除/添加 (纯数值、技能、聚气、触发施放) 行为自检。

全部操作在 sync/Amenda.d2s 的临时副本上进行, 绝不触碰真实存档。
运行: python tests/test_affix_ops.py
"""
import os
import shutil
import sys
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _save_source import ensure_test_save, test_save_path
SRC_SAVE = ensure_test_save()

from d2s.io import load_d2s, save_d2s, verify
from d2s.item_codec import (
    parse_item_list, describe_magic_prop, list_addable_props,
    add_magic_prop, add_magic_prop_ex, delete_magic_prop, patch_magic_value,
)

_PASS = 0


def ok(cond, msg: str) -> None:
    global _PASS
    assert cond, f"断言失败: {msg}"
    _PASS += 1
    print(f"  [通过] {msg}")


def make_tmp_save(tag: str):
    """复制存档到临时目录并加载 (测试完由调用方清理)。"""
    tmp = tempfile.mkdtemp(prefix=f"d2r_test_{tag}_")
    dst = os.path.join(tmp, "Amenda.d2s")
    shutil.copy2(SRC_SAVE, dst)
    return load_d2s(dst), tmp


def reparse(save) -> list:
    return parse_item_list(bytes(save.raw), save.items.offset, version=save.header.version)


def bits_of(data) -> str:
    """字节序列 -> LSB-first 位串 (用于逐位比较)。"""
    return "".join(f"{b:08b}"[::-1] for b in bytes(data))


def check_tail_bits(save, old_raw: bytes, old_end_bit: int, msg: str) -> None:
    """物品词缀位被增删后, 其后所有内容 (后续物品等) 的位序列应逐位一致。
    位级增删会改变字节对齐, 故按位比较文件后缀。"""
    n = len(old_raw) * 8 - old_end_bit
    ok(bits_of(save.raw[-((n + 7) // 8):])[-n:] == bits_of(old_raw[old_end_bit // 8:])[:n], msg)


def props_sig(it: dict) -> list:
    """一个物品词缀表的结构签名: (id, 参数元组, 数值元组) 列表。"""
    return [
        (p["id"],
         tuple(f.get("param") for f in p["fields"]),
         tuple(f.get("value") for f in p["fields"]))
        for p in it.get("magic_attributes", [])
    ]


def all_props_sig(items: list) -> list:
    """整棵物品树 (含镶嵌物) 的词缀签名。"""
    out = []

    def walk(it):
        out.append(props_sig(it))
        for sub in it.get("socketed_items", []) or []:
            walk(sub)

    for it in items:
        walk(it)
    return out


def find_item(items: list, pred):
    def walk(it):
        if pred(it):
            return it
        for sub in it.get("socketed_items", []) or []:
            r = walk(sub)
            if r:
                return r
        return None

    for it in items:
        r = walk(it)
        if r:
            return r
    return None


def get_helm(items):
    """身上槽1头盔 (插入目标)。"""
    return find_item(items, lambda it: it.get("location_id") == 1
                     and it.get("equipped_id") == 1 and it["type"] == "hlm")


def get_dagger(items):
    """Consecrated 长匕首 (item_singleskill 样本, +1 至技能373)。按基础类型 dir 定位。"""
    return find_item(items, lambda it: it["type"] == "dir"
                     and it.get("magic_attributes") is not None
                     and len(it.get("magic_attributes", [])) >= 1)


def get_ring(items):
    """身上槽6聚气戒指 (item_charged_skill 样本, Dim Vision)。"""
    return find_item(items, lambda it: it.get("location_id") == 1
                     and it.get("equipped_id") == 6
                     and any(p["id"] == 204 for p in it.get("magic_attributes", [])))


def last_prop(it: dict) -> dict:
    return it["magic_attributes"][-1]


def check_all_parse(save, expected=67):
    items = reparse(save)
    ok(len(items) == expected, f"全部 {expected} 件物品仍能完整解析 (实际 {len(items)})")
    return items


def check_save_and_verify(save, tag: str):
    save_d2s(save, path=save.path, make_backup=False)
    save2 = load_d2s(save.path)
    ok(verify(save2), f"[{tag}] save_d2s 后重新加载 verify() 校验和为 True")


# ---------------------------------------------------------------------------


def test_baseline():
    print("== 基线: 样本物品解析 ==")
    save, tmp = make_tmp_save("base")
    try:
        items = reparse(save)
        ok(len(items) == 67, f"基线解析 67 件物品 (实际 {len(items)})")
        ring = get_ring(items)
        ok(ring is not None, "找到身上槽6聚气戒指样本")
        p204 = [p for p in ring["magic_attributes"] if p["id"] == 204][0]
        ok(p204["fields"][0]["param"] == 71, f"聚气戒指参数=技能71 Dim Vision (实际 {p204['fields'][0]['param']})")
        ok(p204["values"][0] == 2, f"聚气戒指等级=2 (实际 {p204['values'][0]})")
        ok("charges" in p204["fields"][0], f"聚气戒指解析出充能次数 {p204['fields'][0].get('charges')}")
        dagger = get_dagger(items)
        ok(dagger is not None, "找到 Consecrated 匕首样本")
        p107 = [p for p in dagger["magic_attributes"] if p["id"] == 107][0]
        ok(p107["fields"][0]["param"] == 373 and p107["fields"][0]["value"] == 1,
           f"匕首 singleskill 参数=373 数值=+1 (实际 {p107['fields'][0]['param']}, +{p107['fields'][0]['value']})")
        helm = get_helm(items)
        ok(helm is not None, "找到身上槽1头盔 (插入目标)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_singleskill():
    print("== ③ 删除词缀: Consecrated 匕首的 +1技能 (id=107) ==")
    save, tmp = make_tmp_save("del")
    try:
        items = reparse(save)
        sig_before = all_props_sig(items)
        dagger = get_dagger(items)
        raw_before = bytes(save.raw)
        raw_len_before = len(save.raw)
        prop = [p for p in dagger["magic_attributes"] if p["id"] == 107][0]
        ok(prop["_start_bit"] >= dagger["_props_start_bit"] and prop["_end_bit"] <= dagger["_term_bitpos"],
           f"词缀位位置已记录: [{prop['_start_bit']}, {prop['_end_bit']})")

        delete_magic_prop(save.raw, dagger, prop)

        del_bits = prop["_end_bit"] - prop["_start_bit"]
        ok(len(save.raw) == raw_len_before - ((del_bits + 7) // 8)
           or len(save.raw) == raw_len_before - ((del_bits + 7) // 8) + 1,
           f"文件按删除的位长({del_bits}位, 对齐后 {del_bits//8}-{(del_bits+7)//8} 字节)缩短: "
           f"{raw_len_before} -> {len(save.raw)}")
        items2 = check_all_parse(save)
        dagger2 = get_dagger(items2)
        sig_after = all_props_sig(items2)
        # item[9] = 匕首: 其词缀表去掉 id=107, 其余全部一致
        expect = sig_before[:9] + [[s for s in sig_before[9] if s[0] != 107]] + sig_before[10:]
        ok(sig_after == expect, "删除后其余物品/词缀逐位一致 (全部 id/param/value 签名相同)")
        ok(all(p["id"] != 107 for p in dagger2["magic_attributes"]), "匕首词缀表中 107 已消失")
        # 尾部数据 (后续物品等) 逐位保留
        check_tail_bits(save, raw_before, dagger["_end_bit"], "匕首之后的尾部数据逐位一致")
        check_save_and_verify(save, "删除107")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_charged_and_np_roundtrip():
    print("== ③ 删除词缀: 聚气(204) / np分组 添加后删除还原 ==")
    save, tmp = make_tmp_save("delnp")
    try:
        items = reparse(save)
        ring = get_ring(items)
        p204 = [p for p in ring["magic_attributes"] if p["id"] == 204][0]
        delete_magic_prop(save.raw, ring, p204)
        items2 = check_all_parse(save)
        ring2 = get_ring(items2)
        ok(ring2 is None or all(p["id"] != 204 for p in ring2["magic_attributes"]),
           "聚气词缀 (id=204) 已从戒指删除")

        # np 分组词缀: 添加 -> 再删除 -> 字节完全还原
        # 注意: 每次位流拼接后位偏移全部变化, 必须重新解析再进行下一次操作
        raw_before = bytes(save.raw)
        helm = get_helm(reparse(save))
        add_magic_prop_ex(save.raw, helm, 48, [(None, 5), (None, 12)])  # 火焰伤害 min/max (np=2)
        items3 = check_all_parse(save)
        helm = get_helm(items3)
        add_magic_prop_ex(save.raw, helm, 54, [(None, 3), (None, 9), (None, 40)])  # 冰冷 min/max/时长 (np=3)
        items4 = check_all_parse(save)
        helm4 = get_helm(items4)
        p48 = [p for p in helm4["magic_attributes"] if p["id"] == 48]
        p54 = [p for p in helm4["magic_attributes"] if p["id"] == 54]
        ok(len(p48) == 1 and [f["value"] for f in p48[0]["fields"]] == [5, 12],
           f"np=2 火焰伤害插入读回 {[f['value'] for f in p48[0]['fields']] if p48 else None} == [5, 12]")
        ok(len(p54) == 1 and [f["value"] for f in p54[0]["fields"]] == [3, 9, 40],
           "np=3 冰冷伤害插入读回 == [3, 9, 40]")
        delete_magic_prop(save.raw, helm4, p54[0])
        helm5 = get_helm(check_all_parse(save))
        delete_magic_prop(save.raw, helm5, [p for p in helm5["magic_attributes"] if p["id"] == 48][0])
        ok(bytes(save.raw) == raw_before, "np 分组词缀 添加->删除 后字节流与原始完全一致")
        check_save_and_verify(save, "np往返")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_singleskill():
    print("== ① 添加技能词缀: item_singleskill (id=107) ==")
    save, tmp = make_tmp_save("add107")
    try:
        items = reparse(save)
        helm = get_helm(items)
        add_magic_prop_ex(save.raw, helm, 107, [(373, 1)])  # +1 至技能373 (召唤羊头人)
        items2 = check_all_parse(save)
        helm2 = get_helm(items2)
        p = last_prop(helm2)
        ok(p["id"] == 107, f"插入词缀位于表末尾且 id=107 (实际 {p['id']})")
        ok(p["fields"][0]["param"] == 373, f"读回参数=373 (实际 {p['fields'][0]['param']})")
        ok(p["fields"][0]["value"] == 1, f"读回数值=+1 (实际 {p['fields'][0]['value']})")
        desc = describe_magic_prop(p)
        ok("召唤羊头人" in desc, f"中文描述含技能名: {desc!r}")
        check_save_and_verify(save, "添加107")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_charged():
    print("== ② 添加聚气词缀: item_charged_skill (id=204) ==")
    save, tmp = make_tmp_save("add204")
    try:
        items = reparse(save)
        helm = get_helm(items)
        # 聚气: fields_spec = [((等级, 技能id), (当前次数, 最大次数))]
        add_magic_prop_ex(save.raw, helm, 204, [((5, 71), (18, 25))])  # 5级 微暗灵视 (18/25)
        items2 = check_all_parse(save)
        helm2 = get_helm(items2)
        p = last_prop(helm2)
        ok(p["id"] == 204, f"插入词缀 id=204 (实际 {p['id']})")
        ok(p["values"][0] == 5, f"读回等级=5 (实际 {p['values'][0]})")
        ok(p["fields"][0]["param"] == 71, f"读回参数=技能71 (实际 {p['fields'][0]['param']})")
        ch = p["fields"][0]["charges"]
        ok(ch["cur"] == 18 and ch["max"] == 25, f"读回充能 18/25 (实际 {ch['cur']}/{ch['max']})")
        ok(p["fields"][0]["value"] == 18, "当前充能次数暴露为 field value (只读展示)")
        desc = describe_magic_prop(p)
        ok("微暗灵视" in desc and "18/25" in desc, f"中文描述: {desc!r}")
        check_save_and_verify(save, "添加204")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_cast():
    print("== ② 添加触发施放词缀: item_skillonattack (id=195) ==")
    save, tmp = make_tmp_save("add195")
    try:
        items = reparse(save)
        helm = get_helm(items)
        # 触发施放: fields_spec = [((等级, 技能id), 概率%)]
        add_magic_prop_ex(save.raw, helm, 195, [((10, 37), 20)])  # 20% 施放10级 暖身术
        items2 = check_all_parse(save)
        helm2 = get_helm(items2)
        p = last_prop(helm2)
        ok(p["id"] == 195, f"插入词缀 id=195 (实际 {p['id']})")
        ok(p["values"][0] == 10, f"读回等级=10 (实际 {p['values'][0]})")
        ok(p["fields"][0]["param"] == 37, f"读回参数=技能37 (实际 {p['fields'][0]['param']})")
        ok(p["fields"][0]["value"] == 20, f"读回概率=20% (实际 {p['fields'][0]['value']})")
        desc = describe_magic_prop(p)
        ok("20" in desc and "10" in desc and "暖身术" in desc, f"中文描述: {desc!r}")
        check_save_and_verify(save, "添加195")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_other_param_props():
    print("== ① 其他参数词缀: 技能tab(188) / 职业(83) / 光环(151) / 非本职业技能(97) ==")
    save, tmp = make_tmp_save("addparam")
    try:
        items = reparse(save)
        helm = get_helm(items)
        add_magic_prop_ex(save.raw, helm, 188, [((4, 373), 2)])  # dF14: tab=4, +2 至技能373
        helm = get_helm(check_all_parse(save))
        add_magic_prop_ex(save.raw, helm, 83, [(2, 1)])  # +1 至死灵法师技能等级
        helm = get_helm(check_all_parse(save))
        add_magic_prop_ex(save.raw, helm, 151, [(71, 12)])  # 装备时 12级 微暗灵视灵气
        helm = get_helm(check_all_parse(save))
        add_magic_prop_ex(save.raw, helm, 97, [(373, 3)])  # +3 至非本职业技能373
        items2 = check_all_parse(save)
        helm2 = get_helm(items2)
        props = {p["id"]: p for p in helm2["magic_attributes"]}
        p188 = props[188]
        ok(p188["values"][0] == 4 and p188["fields"][0]["param"] == 373 and p188["fields"][0]["value"] == 2,
           f"188 tab_skill 读回 tab=4 技能=373 数值=+2 (实际 {p188['values'][0]}/{p188['fields'][0]['param']}/+{p188['fields'][0]['value']})")
        p83 = props[83]
        ok(p83["fields"][0]["param"] == 2 and p83["fields"][0]["value"] == 1,
           "83 addclassskills 读回 职业=2(死灵) 数值=+1")
        p151 = props[151]
        ok(p151["fields"][0]["param"] == 71 and p151["fields"][0]["value"] == 12,
           "151 aura 读回 技能=71 等级=12")
        p97 = props[97]
        ok(p97["fields"][0]["param"] == 373 and p97["fields"][0]["value"] == 3,
           "97 nonclassskill 读回 技能=373 数值=+3")
        check_save_and_verify(save, "参数词缀")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_then_delete_identity():
    print("== 往返一致性: 添加107 -> 删除 -> 字节完全还原 ==")
    save, tmp = make_tmp_save("identity")
    try:
        items = reparse(save)
        helm = get_helm(items)
        raw_before = bytes(save.raw)
        add_magic_prop(save.raw, helm, 7, 30)  # 兼容入口: 纯数值 +30 生命
        helm = get_helm(check_all_parse(save))
        add_magic_prop_ex(save.raw, helm, 107, [(373, 2)])
        items2 = check_all_parse(save)
        helm2 = get_helm(items2)
        ok([p["id"] for p in helm2["magic_attributes"]][-2:] == [7, 107],
           "插入两条词缀位于表末尾 (7, 107)")
        # 物品可能已有同 id 词缀, 必须选中"新添加"的那条 (_start_bit 最大)
        p107 = max((p for p in helm2["magic_attributes"] if p["id"] == 107),
                   key=lambda p: p["_start_bit"])
        delete_magic_prop(save.raw, helm2, p107)
        helm3 = get_helm(check_all_parse(save))
        p7 = max((p for p in helm3["magic_attributes"] if p["id"] == 7),
                 key=lambda p: p["_start_bit"])
        delete_magic_prop(save.raw, helm3, p7)
        ok(bytes(save.raw) == raw_before, "添加->删除 后字节流与原始完全一致 (含兼容入口)")
        check_save_and_verify(save, "往返")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_patch_regression():
    print("== 回归: 纯数值修改 (patch_magic_value) ==")
    save, tmp = make_tmp_save("patch")
    try:
        items = reparse(save)
        helm = get_helm(items)
        f = helm["_defense_field"]
        old = f["value"]
        patch_magic_value(save.raw, f, 234)
        items2 = reparse(save)
        helm2 = get_helm(items2)
        ok(helm2["defense_rating"] == 234, f"防御 50->234 重新解析读回 {helm2['defense_rating']}")
        hp = [x for p in helm2["magic_attributes"] for x in p["fields"] if p["id"] == 7][0]
        patch_magic_value(save.raw, hp, 66)
        items3 = reparse(save)
        hp3 = [x for p in get_helm(items3)["magic_attributes"] for x in p["fields"] if p["id"] == 7][0]
        ok(hp3["value"] == 66, f"词缀数值 maxhp 修改后读回 {hp3['value']} == 66")
        check_save_and_verify(save, "数值修改")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_list_addable_props():
    print("== list_addable_props 放宽后的清单 ==")
    props = list_addable_props()
    by_id = {p["id"]: p for p in props}
    ok(107 in by_id and by_id[107]["param_kind"] == "skill", "107 item_singleskill 已加入 (param_kind=skill)")
    ok(204 in by_id and by_id[204]["param_kind"] == "charges", "204 item_charged_skill 已加入 (param_kind=charges)")
    ok(all(i in by_id and by_id[i]["param_kind"] == "cast" for i in (195, 196, 197, 198, 199, 201)),
       "195-201 触发施放词缀已加入 (param_kind=cast)")
    ok(188 in by_id and by_id[188]["param_kind"] == "tab_skill", "188 技能tab词缀已加入")
    ok(83 in by_id and by_id[83]["param_kind"] == "class", "83 addclassskills 已加入 (param_kind=class)")
    ok(151 in by_id and 97 in by_id, "151 光环 / 97 非本职业技能 已加入")
    ok(48 not in by_id and 54 not in by_id, "np 分组词缀 (火焰/冰冷伤害) 不在可添加清单")
    ok(all(i not in by_id for i in (98, 126, 155, 179, 180)), "参数语义未支持的词缀 (state/elemskill/reanimate/montype) 仍排除")
    ok(by_id[107]["min"] == 0 and by_id[107]["max"] == 7, f"107 数值范围 0..7 (实际 {by_id[107]['min']}..{by_id[107]['max']})")
    ok(by_id[204]["min"] == 1 and by_id[204]["max"] == 255, "204 充能次数范围 1..255")
    pure = [p for p in props if p["param_kind"] is None]
    ok(len(pure) >= 158, f"原有纯数值词缀保留 ({len(pure)} 条 >= 158)")
    ok(200 in by_id and by_id[200]["param_kind"] is None, "200 无参数纯数值词缀不受影响")


def test_full_sequence():
    print("== 综合流程: 修改+添加+删除 一次保存 ==")
    save, tmp = make_tmp_save("full")
    try:
        items = reparse(save)
        helm = get_helm(items)
        f = helm["_defense_field"]
        patch_magic_value(save.raw, f, 199)
        add_magic_prop_ex(save.raw, helm, 204, [((3, 71), (10, 10))])
        helm = get_helm(check_all_parse(save))
        add_magic_prop_ex(save.raw, helm, 195, [((20, 37), 50)])
        helm = get_helm(check_all_parse(save))
        add_magic_prop_ex(save.raw, helm, 107, [(373, 1)])
        items2 = check_all_parse(save)
        helm2 = get_helm(items2)
        # 删除中间的触发词缀 (195)
        p195 = [p for p in helm2["magic_attributes"] if p["id"] == 195][0]
        delete_magic_prop(save.raw, helm2, p195)
        items3 = check_all_parse(save)
        helm3 = get_helm(items3)
        ids = [p["id"] for p in helm3["magic_attributes"]]
        ok(195 not in ids and 204 in ids and 107 in ids, f"删除195后其余新词缀保留 (尾部ids: {ids[-3:]})")
        ok(helm3["defense_rating"] == 199, "数值修改在同流程中保持")
        check_save_and_verify(save, "综合")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    tests = [
        test_baseline,
        test_delete_singleskill,
        test_delete_charged_and_np_roundtrip,
        test_add_singleskill,
        test_add_charged,
        test_add_cast,
        test_add_other_param_props,
        test_add_then_delete_identity,
        test_patch_regression,
        test_list_addable_props,
        test_full_sequence,
    ]
    for t in tests:
        t()
    print(f"\n全部通过: {_PASS} 条断言, 0 失败。")


if __name__ == "__main__":
    main()
