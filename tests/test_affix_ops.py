"""Affix delete/add (plain value, skill, charged, chance-to-cast) behavior checks.

All operations run on a temporary copy of sync/Amenda.d2s; the real save is
never touched.
Run: python tests/test_affix_ops.py
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
    parse_item_list, describe_magic_prop, list_addable_props, load_i18n,
    add_magic_prop, add_magic_prop_ex, delete_magic_prop, patch_magic_value,
)

# zh display checks only apply when the user generated the language table;
# without it the editor (and these assertions) fall back to English
HAVE_I18N = bool(load_i18n().get("items"))

_PASS = 0


def ok(cond, msg: str) -> None:
    global _PASS
    assert cond, f"assertion failed: {msg}"
    _PASS += 1
    print(f"  [ok] {msg}")


def make_tmp_save(tag: str):
    """Copy the save to a temp dir and load it (caller cleans up)."""
    tmp = tempfile.mkdtemp(prefix=f"d2r_test_{tag}_")
    dst = os.path.join(tmp, "Amenda.d2s")
    shutil.copy2(SRC_SAVE, dst)
    return load_d2s(dst), tmp


def reparse(save) -> list:
    return parse_item_list(bytes(save.raw), save.items.offset, version=save.header.version)


def bits_of(data) -> str:
    """Byte string -> LSB-first bit string (for bit-exact comparison)."""
    return "".join(f"{b:08b}"[::-1] for b in bytes(data))


def check_tail_bits(save, old_raw: bytes, old_end_bit: int, msg: str) -> None:
    """After adding/deleting affix bits, every bit after the item (following
    items etc.) must stay bit-identical. Bit-level splicing shifts byte
    alignment, so the file suffix is compared bit-wise."""
    n = len(old_raw) * 8 - old_end_bit
    ok(bits_of(save.raw[-((n + 7) // 8):])[-n:] == bits_of(old_raw[old_end_bit // 8:])[:n], msg)


def props_sig(it: dict) -> list:
    """Structural signature of one item's prop list: list of (id, param tuple, value tuple)."""
    return [
        (p["id"],
         tuple(f.get("param") for f in p["fields"]),
         tuple(f.get("value") for f in p["fields"]))
        for p in it.get("magic_attributes", [])
    ]


def all_props_sig(items: list) -> list:
    """Prop signatures of the whole item tree (socketed items included)."""
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
    """Equipped slot 1 helm (insertion target)."""
    return find_item(items, lambda it: it.get("location_id") == 1
                     and it.get("equipped_id") == 1 and it["type"] == "hlm")


def get_dagger(items):
    """Consecrated dirk (item_singleskill sample, +1 to skill 373). Located by
    base type dir."""
    return find_item(items, lambda it: it["type"] == "dir"
                     and it.get("magic_attributes") is not None
                     and len(it.get("magic_attributes", [])) >= 1)


def get_ring(items):
    """Equipped slot 6 charged ring (item_charged_skill sample, Dim Vision)."""
    return find_item(items, lambda it: it.get("location_id") == 1
                     and it.get("equipped_id") == 6
                     and any(p["id"] == 204 for p in it.get("magic_attributes", [])))


def last_prop(it: dict) -> dict:
    return it["magic_attributes"][-1]


def check_all_parse(save, expected=67):
    items = reparse(save)
    ok(len(items) == expected, f"all {expected} items still fully parse (got {len(items)})")
    return items


def check_save_and_verify(save, tag: str):
    save_d2s(save, path=save.path, make_backup=False)
    save2 = load_d2s(save.path)
    ok(verify(save2), f"[{tag}] after save_d2s, reloaded verify() checksum is True")


# ---------------------------------------------------------------------------


def test_baseline():
    print("== baseline: sample item parsing ==")
    save, tmp = make_tmp_save("base")
    try:
        items = reparse(save)
        ok(len(items) == 67, f"baseline parses 67 items (got {len(items)})")
        ring = get_ring(items)
        ok(ring is not None, "found equipped slot 6 charged ring sample")
        p204 = [p for p in ring["magic_attributes"] if p["id"] == 204][0]
        ok(p204["fields"][0]["param"] == 71, f"charged ring param=skill 71 Dim Vision (got {p204['fields'][0]['param']})")
        ok(p204["values"][0] == 2, f"charged ring level=2 (got {p204['values'][0]})")
        ok("charges" in p204["fields"][0], f"charged ring parsed charges {p204['fields'][0].get('charges')}")
        dagger = get_dagger(items)
        ok(dagger is not None, "found Consecrated dagger sample")
        p107 = [p for p in dagger["magic_attributes"] if p["id"] == 107][0]
        ok(p107["fields"][0]["param"] == 373 and p107["fields"][0]["value"] == 1,
           f"dagger singleskill param=373 value=+1 (got {p107['fields'][0]['param']}, +{p107['fields'][0]['value']})")
        helm = get_helm(items)
        ok(helm is not None, "found equipped slot 1 helm (insertion target)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_singleskill():
    print("== 3 delete affix: Consecrated dagger +1 skill (id=107) ==")
    save, tmp = make_tmp_save("del")
    try:
        items = reparse(save)
        sig_before = all_props_sig(items)
        dagger = get_dagger(items)
        raw_before = bytes(save.raw)
        raw_len_before = len(save.raw)
        prop = [p for p in dagger["magic_attributes"] if p["id"] == 107][0]
        ok(prop["_start_bit"] >= dagger["_props_start_bit"] and prop["_end_bit"] <= dagger["_term_bitpos"],
           f"prop bit positions recorded: [{prop['_start_bit']}, {prop['_end_bit']})")

        delete_magic_prop(save.raw, dagger, prop)

        del_bits = prop["_end_bit"] - prop["_start_bit"]
        ok(len(save.raw) == raw_len_before - ((del_bits + 7) // 8)
           or len(save.raw) == raw_len_before - ((del_bits + 7) // 8) + 1,
           f"file shrinks by the deleted bit length ({del_bits} bits, aligned {del_bits//8}-{(del_bits+7)//8} bytes): "
           f"{raw_len_before} -> {len(save.raw)}")
        items2 = check_all_parse(save)
        dagger2 = get_dagger(items2)
        sig_after = all_props_sig(items2)
        # item[9] = dagger: its prop list drops id=107, everything else identical
        expect = sig_before[:9] + [[s for s in sig_before[9] if s[0] != 107]] + sig_before[10:]
        ok(sig_after == expect, "all other items/props bit-identical after deletion (same id/param/value signatures)")
        ok(all(p["id"] != 107 for p in dagger2["magic_attributes"]), "107 gone from the dagger prop list")
        # tail data (following items etc.) preserved bit-by-bit
        check_tail_bits(save, raw_before, dagger["_end_bit"], "tail data after the dagger is bit-identical")
        check_save_and_verify(save, "delete107")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_charged_and_np_roundtrip():
    print("== 3 delete affix: charged (204) / np-group add-then-delete roundtrip ==")
    save, tmp = make_tmp_save("delnp")
    try:
        items = reparse(save)
        ring = get_ring(items)
        p204 = [p for p in ring["magic_attributes"] if p["id"] == 204][0]
        delete_magic_prop(save.raw, ring, p204)
        items2 = check_all_parse(save)
        ring2 = get_ring(items2)
        ok(ring2 is None or all(p["id"] != 204 for p in ring2["magic_attributes"]),
           "charged affix (id=204) deleted from the ring")

        # np-group prop: add -> delete -> exact byte restore
        # note: every bit splice shifts bit offsets; must re-parse before the
        # next operation
        raw_before = bytes(save.raw)
        helm = get_helm(reparse(save))
        add_magic_prop_ex(save.raw, helm, 48, [(None, 5), (None, 12)])  # fire damage min/max (np=2)
        items3 = check_all_parse(save)
        helm = get_helm(items3)
        add_magic_prop_ex(save.raw, helm, 54, [(None, 3), (None, 9), (None, 40)])  # cold min/max/length (np=3)
        items4 = check_all_parse(save)
        helm4 = get_helm(items4)
        p48 = [p for p in helm4["magic_attributes"] if p["id"] == 48]
        p54 = [p for p in helm4["magic_attributes"] if p["id"] == 54]
        ok(len(p48) == 1 and [f["value"] for f in p48[0]["fields"]] == [5, 12],
           f"np=2 fire damage insert reads back {[f['value'] for f in p48[0]['fields']] if p48 else None} == [5, 12]")
        ok(len(p54) == 1 and [f["value"] for f in p54[0]["fields"]] == [3, 9, 40],
           "np=3 cold damage insert reads back == [3, 9, 40]")
        delete_magic_prop(save.raw, helm4, p54[0])
        helm5 = get_helm(check_all_parse(save))
        delete_magic_prop(save.raw, helm5, [p for p in helm5["magic_attributes"] if p["id"] == 48][0])
        ok(bytes(save.raw) == raw_before, "np-group prop add->delete restores the byte stream exactly")
        check_save_and_verify(save, "np roundtrip")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_singleskill():
    print("== 1 add skill affix: item_singleskill (id=107) ==")
    save, tmp = make_tmp_save("add107")
    try:
        items = reparse(save)
        helm = get_helm(items)
        add_magic_prop_ex(save.raw, helm, 107, [(373, 1)])  # +1 to skill 373 (Summon Dire Wolf)
        items2 = check_all_parse(save)
        helm2 = get_helm(items2)
        p = last_prop(helm2)
        ok(p["id"] == 107, f"inserted prop is last in the list with id=107 (got {p['id']})")
        ok(p["fields"][0]["param"] == 373, f"param reads back 373 (got {p['fields'][0]['param']})")
        ok(p["fields"][0]["value"] == 1, f"value reads back +1 (got {p['fields'][0]['value']})")
        if HAVE_I18N:
            desc = describe_magic_prop(p)
            ok("召唤羊头人" in desc, f"zh description contains the skill name: {desc!r}")
        check_save_and_verify(save, "add107")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_charged():
    print("== 2 add charged affix: item_charged_skill (id=204) ==")
    save, tmp = make_tmp_save("add204")
    try:
        items = reparse(save)
        helm = get_helm(items)
        # charged: fields_spec = [((level, skill_id), (cur, max charges))]
        add_magic_prop_ex(save.raw, helm, 204, [((5, 71), (18, 25))])  # level 5 Dim Vision (18/25)
        items2 = check_all_parse(save)
        helm2 = get_helm(items2)
        p = last_prop(helm2)
        ok(p["id"] == 204, f"inserted prop id=204 (got {p['id']})")
        ok(p["values"][0] == 5, f"level reads back 5 (got {p['values'][0]})")
        ok(p["fields"][0]["param"] == 71, f"param reads back skill 71 (got {p['fields'][0]['param']})")
        ch = p["fields"][0]["charges"]
        ok(ch["cur"] == 18 and ch["max"] == 25, f"charges read back 18/25 (got {ch['cur']}/{ch['max']})")
        ok(p["fields"][0]["value"] == 18, "current charges exposed as field value (read-only display)")
        if HAVE_I18N:
            desc = describe_magic_prop(p)
            ok("微暗灵视" in desc and "18/25" in desc, f"zh description: {desc!r}")
        check_save_and_verify(save, "add204")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_cast():
    print("== 2 add chance-to-cast affix: item_skillonattack (id=195) ==")
    save, tmp = make_tmp_save("add195")
    try:
        items = reparse(save)
        helm = get_helm(items)
        # chance-to-cast: fields_spec = [((level, skill_id), chance %)]
        add_magic_prop_ex(save.raw, helm, 195, [((10, 37), 20)])  # 20% chance to cast level 10 Warmth
        items2 = check_all_parse(save)
        helm2 = get_helm(items2)
        p = last_prop(helm2)
        ok(p["id"] == 195, f"inserted prop id=195 (got {p['id']})")
        ok(p["values"][0] == 10, f"level reads back 10 (got {p['values'][0]})")
        ok(p["fields"][0]["param"] == 37, f"param reads back skill 37 (got {p['fields'][0]['param']})")
        ok(p["fields"][0]["value"] == 20, f"chance reads back 20% (got {p['fields'][0]['value']})")
        if HAVE_I18N:
            desc = describe_magic_prop(p)
            ok("20" in desc and "10" in desc and "暖身术" in desc, f"zh description: {desc!r}")
        check_save_and_verify(save, "add195")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_other_param_props():
    print("== 1 other parametric props: skill tab (188) / class (83) / aura (151) / nonclass skill (97) ==")
    save, tmp = make_tmp_save("addparam")
    try:
        items = reparse(save)
        helm = get_helm(items)
        add_magic_prop_ex(save.raw, helm, 188, [((4, 373), 2)])  # dF14: tab=4, +2 to skill 373
        helm = get_helm(check_all_parse(save))
        add_magic_prop_ex(save.raw, helm, 83, [(2, 1)])  # +1 to Necromancer skill levels
        helm = get_helm(check_all_parse(save))
        add_magic_prop_ex(save.raw, helm, 151, [(71, 12)])  # level 12 Dim Vision aura when equipped
        helm = get_helm(check_all_parse(save))
        add_magic_prop_ex(save.raw, helm, 97, [(373, 3)])  # +3 to nonclass skill 373
        items2 = check_all_parse(save)
        helm2 = get_helm(items2)
        props = {p["id"]: p for p in helm2["magic_attributes"]}
        p188 = props[188]
        ok(p188["values"][0] == 4 and p188["fields"][0]["param"] == 373 and p188["fields"][0]["value"] == 2,
           f"188 tab_skill reads back tab=4 skill=373 value=+2 (got {p188['values'][0]}/{p188['fields'][0]['param']}/+{p188['fields'][0]['value']})")
        p83 = props[83]
        ok(p83["fields"][0]["param"] == 2 and p83["fields"][0]["value"] == 1,
           "83 addclassskills reads back class=2 (Necromancer) value=+1")
        p151 = props[151]
        ok(p151["fields"][0]["param"] == 71 and p151["fields"][0]["value"] == 12,
           "151 aura reads back skill=71 level=12")
        p97 = props[97]
        ok(p97["fields"][0]["param"] == 373 and p97["fields"][0]["value"] == 3,
           "97 nonclassskill reads back skill=373 value=+3")
        check_save_and_verify(save, "param props")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_then_delete_identity():
    print("== roundtrip: add 107 -> delete -> exact byte restore ==")
    save, tmp = make_tmp_save("identity")
    try:
        items = reparse(save)
        helm = get_helm(items)
        raw_before = bytes(save.raw)
        add_magic_prop(save.raw, helm, 7, 30)  # compat entry: plain +30 max life
        helm = get_helm(check_all_parse(save))
        add_magic_prop_ex(save.raw, helm, 107, [(373, 2)])
        items2 = check_all_parse(save)
        helm2 = get_helm(items2)
        ok([p["id"] for p in helm2["magic_attributes"]][-2:] == [7, 107],
           "two inserted props at the end of the list (7, 107)")
        # the item may already carry props with the same id; must pick the
        # newly added one (largest _start_bit)
        p107 = max((p for p in helm2["magic_attributes"] if p["id"] == 107),
                   key=lambda p: p["_start_bit"])
        delete_magic_prop(save.raw, helm2, p107)
        helm3 = get_helm(check_all_parse(save))
        p7 = max((p for p in helm3["magic_attributes"] if p["id"] == 7),
                 key=lambda p: p["_start_bit"])
        delete_magic_prop(save.raw, helm3, p7)
        ok(bytes(save.raw) == raw_before, "add->delete restores the byte stream exactly (compat entry included)")
        check_save_and_verify(save, "roundtrip")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_patch_regression():
    print("== regression: plain value edit (patch_magic_value) ==")
    save, tmp = make_tmp_save("patch")
    try:
        items = reparse(save)
        helm = get_helm(items)
        f = helm["_defense_field"]
        old = f["value"]
        patch_magic_value(save.raw, f, 234)
        items2 = reparse(save)
        helm2 = get_helm(items2)
        ok(helm2["defense_rating"] == 234, f"defense 50->234 re-parses and reads back {helm2['defense_rating']}")
        hp = [x for p in helm2["magic_attributes"] for x in p["fields"] if p["id"] == 7][0]
        patch_magic_value(save.raw, hp, 66)
        items3 = reparse(save)
        hp3 = [x for p in get_helm(items3)["magic_attributes"] for x in p["fields"] if p["id"] == 7][0]
        ok(hp3["value"] == 66, f"maxhp affix value reads back {hp3['value']} == 66 after edit")
        check_save_and_verify(save, "value edit")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_list_addable_props():
    print("== list_addable_props after the parametric expansion ==")
    props = list_addable_props()
    by_id = {p["id"]: p for p in props}
    ok(107 in by_id and by_id[107]["param_kind"] == "skill", "107 item_singleskill added (param_kind=skill)")
    ok(204 in by_id and by_id[204]["param_kind"] == "charges", "204 item_charged_skill added (param_kind=charges)")
    ok(all(i in by_id and by_id[i]["param_kind"] == "cast" for i in (195, 196, 197, 198, 199, 201)),
       "195-201 chance-to-cast props added (param_kind=cast)")
    ok(188 in by_id and by_id[188]["param_kind"] == "tab_skill", "188 skill tab prop added")
    ok(83 in by_id and by_id[83]["param_kind"] == "class", "83 addclassskills added (param_kind=class)")
    ok(151 in by_id and 97 in by_id, "151 aura / 97 nonclass skill added")
    ok(48 not in by_id and 54 not in by_id, "np-group props (fire/cold damage) not in the addable list")
    ok(all(i not in by_id for i in (98, 126, 155, 179, 180)), "props with unsupported param semantics (state/elemskill/reanimate/montype) still excluded")
    ok(by_id[107]["min"] == 0 and by_id[107]["max"] == 7, f"107 value range 0..7 (got {by_id[107]['min']}..{by_id[107]['max']})")
    ok(by_id[204]["min"] == 1 and by_id[204]["max"] == 255, "204 charge count range 1..255")
    pure = [p for p in props if p["param_kind"] is None]
    ok(len(pure) >= 158, f"original plain-value props kept ({len(pure)} >= 158)")
    ok(200 in by_id and by_id[200]["param_kind"] is None, "200 no-param plain prop unaffected")


def test_full_sequence():
    print("== combined flow: edit + add + delete in one save ==")
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
        # delete the middle chance-to-cast prop (195)
        p195 = [p for p in helm2["magic_attributes"] if p["id"] == 195][0]
        delete_magic_prop(save.raw, helm2, p195)
        items3 = check_all_parse(save)
        helm3 = get_helm(items3)
        ids = [p["id"] for p in helm3["magic_attributes"]]
        ok(195 not in ids and 204 in ids and 107 in ids, f"after deleting 195 the other new props remain (tail ids: {ids[-3:]})")
        ok(helm3["defense_rating"] == 199, "value edit survives the same flow")
        check_save_and_verify(save, "combined")
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
    print(f"\nall passed: {_PASS} assertions, 0 failures.")


if __name__ == "__main__":
    main()
