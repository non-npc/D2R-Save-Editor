"""zh-CN display self-check for added affixes (tests/test_affix_i18n.py).

1) All list_addable_props dropdown descriptions are zh-CN (official zhCN
   templates / labeled neutral wording);
2) For every prop, insert -> re-parse -> describe_magic_prop display is also
   zh-CN, with values round-tripping exactly;
3) stat 83 class skill levels show the per-class official string
   (incl. Sorceress/Assassin);
4) Localization is display-only: insert then delete restores the bit stream
   byte-for-byte (write-back data is never affected).

All operations run on a temporary copy of sync/Amenda.d2s; the real save is
never touched.
The whole suite is skipped when d2s/data/i18n_zh.json has not been generated
(upstream English environments) - without the table every display falls back
to English by design.
Run: python tests/test_affix_i18n.py
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
    parse_item_list, describe_magic_prop, list_addable_props, load_i18n,
    add_magic_prop_ex, delete_magic_prop,
)
from app.main import affix_fields_spec

# graceful skip when the optional language table was never generated
if not load_i18n().get("items"):
    print("[skip] d2s/data/i18n_zh.json not found (generate it with "
          "tools/build_i18n.py); zh-CN display checks need the table.")
    sys.exit(0)

_PASS = 0


def ok(cond, msg: str) -> None:
    global _PASS
    assert cond, f"assertion failed: {msg}"
    _PASS += 1
    print(f"  [ok] {msg}")


def make_tmp_save(tag: str):
    """Copy the save to a temp dir and load it (caller cleans up)."""
    tmp = tempfile.mkdtemp(prefix=f"d2r_i18n_{tag}_")
    dst = os.path.join(tmp, "Amenda.d2s")
    shutil.copy2(SRC_SAVE, dst)
    return load_d2s(dst), tmp


def reparse(save) -> list:
    return parse_item_list(bytes(save.raw), save.items.offset, version=save.header.version)


def get_helm(items):
    """Equipped slot 1 helm (insertion target), same locator as test_affix_ops."""
    for it in items:
        if (it.get("location_id") == 1 and it.get("equipped_id") == 1
                and it["type"] == "hlm"):
            return it
    return None


_PH = re.compile(r"%\+?d|%s|%%")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_EN = re.compile(r"[A-Za-z]")


def is_zh_desc(text: str) -> bool:
    """zh text: contains CJK and, after stripping %d/%s/%% placeholders, no
    Latin letters."""
    return bool(_CJK.search(text)) and not _EN.search(_PH.sub("", text))


def test_dropdown_zh():
    print("== dropdown: all 170 addable prop descriptions are zh-CN ==")
    props = list_addable_props()
    ok(len(props) == 170, f"170 addable props (got {len(props)})")
    bad = [(p["id"], p["name"], p["desc"]) for p in props if not is_zh_desc(p["desc"])]
    ok(not bad, f"all 170 dropdown descriptions are zh-CN (English leftovers: {bad})")
    # neutral param wording: stat 83 / 188 no longer show the official template
    # that hardcodes the first param value
    d83 = next(p["desc"] for p in props if p["id"] == 83)
    ok("职业" in d83, f"stat 83 dropdown wording is neutral: {d83!r}")
    d188 = next(p["desc"] for p in props if p["id"] == 188)
    ok("技能页" in d188, f"stat 188 dropdown wording is neutral: {d188!r}")


def test_insert_display_roundtrip():
    print("== insert smoke: all 170 props one by one, insert -> re-parse -> table display ==")
    save, tmp = make_tmp_save("insert")
    try:
        items = reparse(save)
        helm = get_helm(items)
        ok(helm is not None, "found equipped slot 1 helm (insertion target)")
        n_orig = len(helm["magic_attributes"])
        props = list_addable_props()
        bad_desc, bad_id, bad_val = [], [], []
        for p in props:
            # value clamped into the prop's legal range (a few props such as
            # item_damagetargetac use offset encoding with negative ranges)
            v = max(p["min"], min(7, p["max"]))
            add_magic_prop_ex(save.raw, helm, p["id"],
                              affix_fields_spec(p, value=v, skill_id=36, tab=0,
                                                class_id=1, level=2, cur=3, mx=4))
            items = reparse(save)  # re-parse after insert (real UI path)
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
        ok(not bad_id, f"all 170 props read back the same id after insert (bad: {bad_id})")
        ok(not bad_val, f"plain props round-trip value 7 exactly (bad: {bad_val})")
        ok(not bad_desc, f"table display is zh-CN after insert (bad: {bad_desc})")
        ok(len(helm["magic_attributes"]) == n_orig + len(props),
           f"helm prop count = original {n_orig} + inserted {len(props)} (got {len(helm['magic_attributes'])})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_delete_byte_restore():
    print("== bit-stream safety: insert one prop then delete it, file restored byte-for-byte "
          "(localization never affects write-back) ==")
    save, tmp = make_tmp_save("restore")
    try:
        items = reparse(save)
        helm = get_helm(items)
        raw_before = bytes(save.raw)
        p7 = next(p for p in list_addable_props() if p["id"] == 7)  # +7 life
        add_magic_prop_ex(save.raw, helm, 7, affix_fields_spec(p7, value=7))
        items = reparse(save)
        helm = get_helm(items)
        ok(helm["magic_attributes"][-1]["id"] == 7, "inserted +7 life (id=7)")
        delete_magic_prop(save.raw, helm, helm["magic_attributes"][-1])
        ok(bytes(save.raw) == raw_before, "deleting the just-inserted prop restores the file byte-for-byte")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_stat83_class_templates():
    print("== stat 83 class skill levels: official per-class wording ==")
    expect = {0: "亚马逊", 1: "巫师", 2: "死灵法师", 3: "圣骑士",
              4: "野蛮人", 5: "德鲁伊", 6: "猎法者"}
    bad = []
    for cls, name in expect.items():
        prop = {"id": 83, "name": "item_addclassskills",
                "fields": [{"param": cls, "value": 3}]}
        desc = describe_magic_prop(prop)
        if name not in desc or not is_zh_desc(desc):
            bad.append((cls, desc))
    ok(not bad, f"all 7 classes show their official wording (bad: {bad})")


def test_i18n_data_integrity():
    print("== i18n data integrity ==")
    i18n = load_i18n()
    stat_tpl = i18n.get("stat_tpl", {})
    cls_tpl = i18n.get("class_skill_tpl", {})
    props = list_addable_props()
    missing = [p["id"] for p in props if str(p["id"]) not in stat_tpl]
    ok(not missing, f"all 170 addable props have zh templates (missing: {missing})")
    ok(sorted(cls_tpl, key=int) == [str(i) for i in range(7)],
       f"class_skill_tpl covers 7 classes (got {sorted(cls_tpl, key=int)})")
    ok(len(stat_tpl) >= 221, f"stat_tpl has {len(stat_tpl)} entries (>= original 221)")


if __name__ == "__main__":
    test_i18n_data_integrity()
    test_dropdown_zh()
    test_insert_display_roundtrip()
    test_stat83_class_templates()
    test_add_delete_byte_restore()
    print(f"\naffix zh-CN display all passed: {_PASS} assertions.")
