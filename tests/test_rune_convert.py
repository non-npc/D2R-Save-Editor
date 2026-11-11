"""Rune conversion behavior checks: change_item_type bit surgery + the
ItemsTab rune conversion controls.

Everything runs on a temporary copy of sync/Amenda.d2s; the real save under
Saved Games is never touched.
Run:
  python tests/test_rune_convert.py           (pure codec parts)
  also fine under QT_QPA_PLATFORM=offscreen   (see the UI part's skip logic)
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
    parse_item_list, describe_item, change_item_type, load_i18n, load_constants,
    encode_type_code,
)
from app.main import RUNE_EN_NAMES

# display-text expectations switch on the generated language table
HAVE_I18N = bool(load_i18n().get("items"))
ITEMS_I18N = load_i18n().get("items", {})


def span_end_of(items, idx: int):
    """End of the bit span the item actually occupies (= next top-level item's
    start bit; its trailing zero alignment byte travels with the item)."""
    nxt = items[idx + 1] if idx + 1 < len(items) else None
    return nxt["_start_bit"] if nxt is not None else None


_PASS = 0


def ok(cond, msg: str) -> None:
    global _PASS
    assert cond, f"assertion failed: {msg}"
    _PASS += 1
    print(f"  [ok] {msg}")


def make_tmp_save(tag: str):
    """Copy the save to a temp dir and load it (caller cleans up)."""
    tmp = tempfile.mkdtemp(prefix=f"d2r_test_rune_{tag}_")
    dst = os.path.join(tmp, "Amenda.d2s")
    shutil.copy2(SRC_SAVE, dst)
    return load_d2s(dst), tmp


def reparse(save) -> list:
    return parse_item_list(bytes(save.raw), save.items.offset, version=save.header.version)


def find_rune(items, code: str):
    for i, it in enumerate(items):
        if (it.get("type") or "").strip() == code:
            return i, it
    return -1, None


def loc_sig(it: dict) -> tuple:
    """Location signature: (location_id, equipped_id, alt_position_id, x, y) —
    conversions must never change it."""
    return (it.get("location_id"), it.get("equipped_id"), it.get("alt_position_id"),
            it.get("position_x"), it.get("position_y"))


def items_sig(items: list) -> list:
    """(type code, location signature) of every item — must match item-by-item
    after a roundtrip conversion."""
    return [((it.get("type") or "").strip(), loc_sig(it)) for it in items]


def save_and_verify(save, tag: str):
    save_d2s(save, path=save.path, make_backup=False)
    save2 = load_d2s(save.path)
    ok(verify(save2), f"[{tag}] after save_d2s, reloaded verify() checksum is True")


def rune_label(code: str) -> str:
    """Expected combo display for a rune: '<zh> (<En>)' with the language
    table, else '<En> (<code>)'."""
    en = RUNE_EN_NAMES[code]
    zh = ITEMS_I18N.get(code)
    return f"{zh} ({en})" if zh else f"{en} ({code})"


# ---------------------------------------------------------------------------


def test_i18n_rune_coverage():
    print("== i18n: r01-r33 zh coverage ==")
    items = load_i18n().get("items", {})
    missing = [c for c in sorted(RUNE_EN_NAMES) if not items.get(c)]
    ok(not missing, f"all r01-r33 have zh names (missing: {missing or 'none'})")
    ok(len(RUNE_EN_NAMES) == 33, f"code table has 33 entries (got {len(RUNE_EN_NAMES)})")
    ok(items.get("r07") == "塔尔符文" and items.get("r33") == "萨德符文",
       f"r07={items.get('r07')!r} r33={items.get('r33')!r}")
    # the base item tables must also resolve r07 / r33 (the type codes must
    # really exist in the game data)
    constants = load_constants()
    for code in ("r07", "r33"):
        found = any(code in constants[t] for t in ("armor_items", "weapon_items", "other_items"))
        ok(found, f"{code} exists in the base item tables (parseable, writable)")


def test_convert_r07_to_r33():
    print("== convert: stash Tal Rune (r07) -> Zod (r33) ==")
    save, tmp = make_tmp_save("to33")
    try:
        items = reparse(save)
        ok(len(items) == 67, f"baseline parses 67 items (got {len(items)})")
        idx, rune = find_rune(items, "r07")
        ok(rune is not None, f"found Tal Rune (r07) sample at index {idx}")
        ok(rune.get("simple_item") == 1, "rune is a simple item (simple_item==1, type change supported)")
        loc_before = loc_sig(rune)
        sig_before = items_sig(items)
        span_end = span_end_of(items, idx)
        ok(span_end is not None and span_end - rune["_end_bit"] == 8,
           f"rune has a trailing zero alignment/stack byte (span_end - _end_bit = {span_end - rune['_end_bit']})")
        raw_before = bytes(save.raw)
        n_before = len(save.raw)

        change_item_type(save.raw, rune, "r33", span_end=span_end)

        ok(len(save.raw) == n_before, f"growing conversion (r07 20 bits -> r33 21 bits) keeps file length {n_before}")
        ok(bytes(save.raw[span_end // 8:]) == raw_before[span_end // 8:],
           "bytes after the item span unchanged (other items untouched)")
        items2 = reparse(save)
        ok(len(items2) == 67, "67 items still fully parse after conversion (count unchanged)")
        idx2, rune2 = find_rune(items2, "r33")
        ok(idx2 == idx and rune2 is not None, f"re-parse reads back type 'r33' (same index {idx2})")
        ok(loc_sig(rune2) == loc_before, f"location unchanged: {loc_sig(rune2)}")
        title = describe_item(rune2)["title"]
        ok("萨德" in title if HAVE_I18N else "Zod" in title, f"title shows the rune name: {title!r}")
        ok(all((it.get("type") or "").strip() != "r07" for it in items2), "original r07 gone")
        sig_after = list(items_sig(items2))
        sig_after[idx2] = sig_before[idx]  # the target item itself is r33 now
        ok(sig_after == sig_before, "other 66 items type/location identical after conversion")
        save_and_verify(save, "r07->r33")

        # roundtrip: r33 -> r07, must restore the original byte stream exactly
        items3 = reparse(save)
        _, rune3 = find_rune(items3, "r33")
        change_item_type(save.raw, rune3, "r07", span_end=span_end_of(items3, idx))
        items4 = reparse(save)
        _, rune4 = find_rune(items4, "r07")
        ok(rune4 is not None and loc_sig(rune4) == loc_before, "converted back to 'r07': type and location match")
        ok(items_sig(items4) == sig_before, "after the roundtrip all 67 items type/location match the baseline")
        save_and_verify(save, "r33->r07")
        # with contents restored, the checksum save_d2s recomputes matches the
        # original file -> the whole file is restored byte-for-byte
        ok(bytes(save.raw) == raw_before, "after the roundtrip + save the whole file is byte-identical to the original")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_roundtrip_byte_identity():
    print("== byte restore: equal Huffman bit length target codes (r07<->r09, both 20 bits) roundtrip ==")
    save, tmp = make_tmp_save("identity")
    try:
        items = reparse(save)
        idx, rune = find_rune(items, "r07")
        ok(rune is not None, "found Tal Rune (r07)")
        n07 = len(encode_type_code("r07 "))
        n09 = len(encode_type_code("r09 "))
        ok(n07 == n09, f"r07/r09 type codes have equal bit length ({n07} == {n09}, byte restore feasible)")
        raw_before = bytes(save.raw)
        change_item_type(save.raw, rune, "r09", span_end=span_end_of(reparse(save), idx))
        items2 = reparse(save)
        idx2, rune2 = find_rune(items2, "r09")
        ok(idx2 == idx and rune2 is not None, "reads back type 'r09' (same index)")
        change_item_type(save.raw, rune2, "r07", span_end=span_end_of(items2, idx))
        items3 = reparse(save)
        ok(find_rune(items3, "r07")[0] == idx, "converted back to 'r07'")
        ok(bytes(save.raw) == raw_before, "equal-length roundtrip restores the byte stream exactly")
        save_and_verify(save, "r09 roundtrip")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sweep_all_33_codes():
    print("== sweep: r07 converted to all 33 target codes r01..r33 in turn, then back ==")
    save, tmp = make_tmp_save("sweep")
    try:
        items = reparse(save)
        idx, rune = find_rune(items, "r07")
        ok(rune is not None, "found Tal Rune (r07)")
        sig_before = items_sig(items)
        loc_before = loc_sig(rune)
        raw_before = bytes(save.raw)
        n_before = len(save.raw)
        cur = rune
        for i in range(1, 34):
            code = f"r{i:02d}"
            items_now = reparse(save)
            cur = find_rune(items_now, (cur.get("type") or "").strip())[1]
            change_item_type(save.raw, cur, code, span_end=span_end_of(items_now, idx))
            items2 = reparse(save)
            ok(len(save.raw) == n_before, f"-> {code} file length unchanged")
            cur = find_rune(items2, code)[1]
            ok(cur is not None and loc_sig(cur) == loc_before,
               f"-> {code} ({RUNE_EN_NAMES[code]}) reads back and keeps its location")
        items3 = reparse(save)
        change_item_type(save.raw, find_rune(items3, "r33")[1], "r07",
                         span_end=span_end_of(items3, idx))
        back = find_rune(reparse(save), "r07")[1]
        ok(back is not None, "converted back to r07")
        ok(items_sig(reparse(save)) == sig_before, "after 33 conversions all items type/location match the baseline")
        ok(bytes(save.raw) == raw_before, "after 33 conversions the whole file byte stream matches the original")
        save_and_verify(save, "sweep")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_reject_invalid():
    print("== reject: non-simple items / invalid type codes ==")
    save, tmp = make_tmp_save("reject")
    try:
        items = reparse(save)
        helm = next(it for it in items if it.get("type") == "hlm")
        ok(helm.get("simple_item") != 1, "helm is not a simple item (advanced)")
        try:
            change_item_type(save.raw, helm, "r33")
            ok(False, "non-simple item must raise ValueError")
        except ValueError:
            ok(True, "non-simple item raises ValueError (rejected)")
        _, rune = find_rune(items, "r07")
        try:
            change_item_type(save.raw, rune, "r@@")
            ok(False, "invalid type code must raise ValueError")
        except ValueError:
            ok(True, "invalid type code (not Huffman-encodable) raises ValueError")
        # growing conversion with no trailing padding available (span_end =
        # _end_bit) -> rejected, save untouched
        raw_before = bytes(save.raw)
        try:
            change_item_type(save.raw, rune, "r04", span_end=rune["_end_bit"])  # 20->23 bits
            ok(False, "growing conversion without padding must raise ValueError")
        except ValueError:
            ok(True, "growing conversion with no zero padding raises ValueError (rejected)")
        try:
            change_item_type(save.raw, rune, "r05", span_end=0)  # bad span
            ok(False, "bad span must raise ValueError")
        except ValueError:
            ok(True, "bad span_end (0) raises ValueError (rejected)")
        ok(bytes(save.raw) == raw_before, "rejection paths never modify any byte")
        ok(find_rune(reparse(save), "r07")[1] is not None, "save not corrupted after rejections (r07 still parses)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ui_rune_convert():
    print("== UI: rune conversion controls (offscreen, dialogs stubbed) ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from app.main import MainWindow
    except Exception as e:  # pragma: no cover
        print(f"  [skip] PyQt6 unavailable: {e}")
        return
    shown = []
    QMessageBox.information = lambda *a, **k: shown.append("info") or QMessageBox.StandardButton.Ok
    QMessageBox.critical = lambda *a, **k: shown.append("critical") or QMessageBox.StandardButton.Ok

    tmp = tempfile.mkdtemp(prefix="d2r_test_rune_ui_")
    dst = os.path.join(tmp, "Amenda.d2s")
    shutil.copy2(SRC_SAVE, dst)
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.save = load_d2s(dst)
    win.dirty = False
    win._refresh_ui()
    tab = win.items
    try:
        combo = tab.rune_combo
        ok(combo.count() == 34, f"rune combo has 34 entries (33 runes + placeholder, got {combo.count()})")
        placeholder = "选择目标符文…" if HAVE_I18N else "Select target rune…"
        ok(combo.itemText(0) == placeholder and combo.itemData(0) is None,
           f"placeholder shows {combo.itemText(0)!r} with itemData=None")
        i_r33 = next(i for i in range(combo.count()) if combo.itemData(i) == "r33")
        i_r07 = next(i for i in range(combo.count()) if combo.itemData(i) == "r07")
        ok(rune_label("r33") == combo.itemText(i_r33), f"r33 entry shows {combo.itemText(i_r33)!r}")
        ok(rune_label("r07") == combo.itemText(i_r07), f"r07 entry shows {combo.itemText(i_r07)!r}")
        ok(not tab.rune_convert_btn.isEnabled() and not combo.isEnabled(),
           "controls disabled initially (non-rune item)")

        idx, _ = find_rune(tab.full_items, "r07")
        ok(idx >= 0, f"found r07 in full_items (index {idx})")
        tab.item_combo.setCurrentIndex(idx)  # triggers _show_props
        ok(tab.rune_convert_btn.isEnabled() and combo.isEnabled(),
           "controls enabled after selecting a rune")
        # placeholder + convert click -> info dialog, nothing changed
        tab.rune_convert_btn.click()
        ok("info" in shown, "convert click with placeholder (no target) shows an info dialog")
        ok(win.dirty is False, "not marked dirty without a target")
        ok(find_rune(reparse(win.save), "r07")[0] == idx, "item unchanged without a target")

        # real conversion: r07 -> r33
        combo.setCurrentIndex(i_r33)
        tab.rune_convert_btn.click()
        ok(win.dirty, "marked dirty after conversion")
        items2 = reparse(win.save)
        idx2, rune2 = find_rune(items2, "r33")
        ok(idx2 == idx and rune2 is not None, f"re-parse reads back type 'r33' (same index {idx2})")
        needle = "萨德" if HAVE_I18N else "Zod"
        ok(needle in tab.item_combo.itemText(idx), f"item combo text updated: {tab.item_combo.itemText(idx)!r}")
        ok(combo.currentIndex() == 0, "combo reset to the placeholder after a successful conversion")
        ok(tab.rune_convert_btn.isEnabled(), "still a rune after conversion, controls stay enabled")

        # convert back to r07 (roundtrip)
        combo.setCurrentIndex(i_r07)
        tab.rune_convert_btn.click()
        items3 = reparse(win.save)
        ok(find_rune(items3, "r07")[0] == idx, "converted back to 'r07': re-parse reads back the type")
        ok(find_rune(items3, "r33")[0] == -1, "r33 gone")
        save_and_verify(win.save, "UI roundtrip")

        # cell refresh: temporarily treat the converted item as an inventory
        # cell (3,2); _populate_cells should show the new rune name
        it = tab.full_items[idx]
        it["location_id"], it["alt_position_id"] = 0, 1
        it["position_x"], it["position_y"] = 3, 2
        tab._populate_cells()
        lbl = tab.inv_cells[(3, 2)]
        ok("符文" in lbl.text() if HAVE_I18N else "Rune" in lbl.text(),
           f"inventory cell (3,2) refreshed display: {lbl.text()!r}")

        # switch back to a non-rune item -> controls disabled
        tab.item_combo.setCurrentIndex(10)
        ok(not tab.rune_convert_btn.isEnabled() and not combo.isEnabled(),
           "controls disabled after switching to a non-rune item")
    finally:
        win.close()
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_i18n_rune_coverage()
    test_convert_r07_to_r33()
    test_roundtrip_byte_identity()
    test_sweep_all_33_codes()
    test_reject_invalid()
    test_ui_rune_convert()
    print(f"\nrune conversion self-check all passed: {_PASS} assertions, 0 failures.")


if __name__ == "__main__":
    main()
