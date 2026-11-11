"""UI smoke test (offscreen): main window bound to a save copy; affix
add/delete exercised through the real UI code paths.

Run: QT_QPA_PLATFORM=offscreen python tests/test_ui_smoke.py
Everything operates on a temporary copy; the real save under Saved Games is
never touched.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil
import sys
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from d2s.io import load_d2s, verify
from d2s.item_codec import list_addable_props, parse_item_list, load_i18n
from app.main import MainWindow, affix_fields_spec, make_skill_combo

from _save_source import ensure_test_save, test_save_path
SRC_SAVE = ensure_test_save()

# display-text expectations switch on the generated language table; without it
# the UI (and these assertions) use the English fallbacks
HAVE_I18N = bool(load_i18n().get("items"))

_PASS = 0


def ok(cond, msg: str) -> None:
    global _PASS
    assert cond, f"assertion failed: {msg}"
    _PASS += 1
    print(f"  [ok] {msg}")


def find_row_with_text(tab, col: int, text: str) -> int:
    for r in range(tab.props_table.rowCount()):
        it = tab.props_table.item(r, col)
        if it and text in it.text():
            return r
    return -1


def main():
    tmp = tempfile.mkdtemp(prefix="d2r_ui_smoke_")
    dst = os.path.join(tmp, "Amenda.d2s")
    shutil.copy2(SRC_SAVE, dst)

    # silence modal dialogs (record calls only)
    shown = []
    QMessageBox.information = lambda *a, **k: shown.append("info") or QMessageBox.StandardButton.Ok
    QMessageBox.question = lambda *a, **k: shown.append("question") or QMessageBox.StandardButton.Yes
    QMessageBox.critical = lambda *a, **k: shown.append("critical") or QMessageBox.StandardButton.Ok

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.save = load_d2s(dst)
    win.dirty = False
    win._refresh_ui()
    tab = win.items
    try:
        print("== main window binding ==")
        ok(win.tabs.isTabEnabled(win.tabs.indexOf(tab)), "items tab enabled")
        ok(tab.item_combo.count() == 67, f"item combo has 67 entries (got {tab.item_combo.count()})")
        ok(tab.props_table.columnCount() == 5, "affix table has 5 columns (incl. action column)")

        print("== select helm and inspect affixes ==")
        tab.item_combo.setCurrentIndex(10)
        tab._show_props(10)
        ok(tab.props_table.rowCount() >= 2, f"helm affix rows {tab.props_table.rowCount()} >= 2")
        del_btns = [tab.props_table.cellWidget(r, 4) for r in range(tab.props_table.rowCount())
                    if tab.props_table.cellWidget(r, 4) is not None]
        ok(len(del_btns) >= 2, f"every affix row has a delete button ({len(del_btns)})")

        print("== skill combo ==")
        combo = make_skill_combo()
        ok(combo.count() == 429, f"skill combo has 429 entries (got {combo.count()})")
        needle = "微暗灵视" if HAVE_I18N else "Dim Vision"
        hit = [i for i in range(combo.count()) if needle in combo.itemText(i)]
        ok(bool(hit) and combo.itemData(hit[0]) == 71, f"searching {needle!r} -> skill id {combo.itemData(hit[0])}")

        print("== add-affix dialog param visibility ==")
        props = list_addable_props()
        dlg, c, vs, w = tab._build_affix_dialog("smoke test", props)
        i204 = next(i for i in range(c.count()) if c.itemData(i)["id"] == 204)
        c.setCurrentIndex(i204)
        ok(not w["lbl_cur"].isHidden(), "charged prop shows the current-charges input")
        ok(not w["max_spin"].isHidden(), "charged prop shows the max-charges input")
        ok(w["lbl_tab"].isHidden(), "charged prop hides the skill-tab input")
        i195 = next(i for i in range(c.count()) if c.itemData(i)["id"] == 195)
        c.setCurrentIndex(i195)
        ok(not w["level_spin"].isHidden(), "trigger prop shows the skill-level input")
        ok(w["lbl_cur"].isHidden(), "trigger prop hides the charges input")
        ok("概率" in w["lbl_value"].text() or "Chance" in w["lbl_value"].text(),
           f"trigger prop value label = {w['lbl_value'].text()!r}")
        i7 = next(i for i in range(c.count()) if c.itemData(i)["id"] == 7)
        c.setCurrentIndex(i7)
        ok(w["skill_combo"].isHidden() and not w["value_spin"].isHidden(), "plain prop shows only the value input")
        dlg.deleteLater()

        print("== UI add charged affix (_do_add_affix) ==")
        dim = "微暗灵视" if HAVE_I18N else "Dim Vision"
        p204 = next(p for p in props if p["id"] == 204)
        spec = affix_fields_spec(p204, skill_id=71, level=5, cur=18, mx=25)
        tab._do_add_affix(win.save, 10, p204, spec)
        ok(win.dirty, "dirty flag set after add")
        row = find_row_with_text(tab, 0, dim)
        ok(row >= 0, f"affix table shows the new prop row (row {row})")
        ok("18/25" in tab.props_table.item(row, 0).text(), f"row text contains charges: {tab.props_table.item(row, 0).text()!r}")
        items = parse_item_list(bytes(win.save.raw), win.save.items.offset, version=win.save.header.version)
        ok(len(items) == 67, "all 67 items still fully parse after the add")

        print("== UI delete affix (delete button click) ==")
        btn = tab.props_table.cellWidget(row, 4)
        ok(btn is not None, "new affix row has a delete button")
        btn.click()
        ok("question" in shown, "confirmation dialog shown before delete")
        row_after = find_row_with_text(tab, 0, dim)
        ok(row_after < 0, "affix row gone after delete")
        items2 = parse_item_list(bytes(win.save.raw), win.save.items.offset, version=win.save.header.version)
        helm = items2[10]
        ok(all(p["id"] != 204 for p in helm["magic_attributes"]), "charged prop deleted from the helm")
        ok(len(items2) == 67, "all 67 items still fully parse after the delete")

        print("== UI add skill affix (singleskill) ==")
        p107 = next(p for p in props if p["id"] == 107)
        spec = affix_fields_spec(p107, skill_id=373, value=2)
        tab._do_add_affix(win.save, 10, p107, spec)
        row = find_row_with_text(tab, 0, "召唤羊头人" if HAVE_I18N else "Summon Dire Wolf")
        ok(row >= 0, "affix table shows +2 to the skill")
        items3 = parse_item_list(bytes(win.save.raw), win.save.items.offset, version=win.save.header.version)
        p = items3[10]["magic_attributes"][-1]
        ok(p["id"] == 107 and p["fields"][0]["param"] == 373 and p["fields"][0]["value"] == 2,
           "re-parse reads back identical id/param/value")

        print("== cell display and click selection ==")
        # full-parse fill: equipped slot shows the item name (full_items[10] = helm, equipped_id=1)
        helm_lbl = tab.equipped_slots[1]
        ok("头盔" in helm_lbl.text() if HAVE_I18N else "Cap" in helm_lbl.text(),
           f"helm cell shows the item name: {helm_lbl.text()!r}")
        book_lbl = tab.inv_cells[(0, 0)]
        book_name = "城镇传送之书" if HAVE_I18N else "Town Portal Book"
        ok(book_name in book_lbl.text() and "×27" in book_lbl.text(),
           f"inventory cell (0,0) shows name and quantity: {book_lbl.text()!r}")
        empty_lbl = tab.inv_cells[(2, 0)]
        ok(empty_lbl.text() == "—", "empty inventory cell keeps the placeholder")

        # simulate click handler: helm cell -> combo points at index 10
        tab._select_by_slot("equipped", 1)
        ok(tab.item_combo.currentIndex() == 10,
           f"clicking the helm cell -> combo index {tab.item_combo.currentIndex()}")
        ok(tab.props_table.rowCount() > 0, "affix table has rows after cell click")
        ok("c7b377" in tab._equipped_frames[1].styleSheet(), "selected cell border highlighted")

        # real mouse click on inventory cell (0,0) Town Portal Book (full_items index 64)
        QTest.mouseClick(tab.inv_cells[(0, 0)], Qt.MouseButton.LeftButton)
        ok(tab.item_combo.currentIndex() == 64,
           f"mouse click on inventory cell -> combo index {tab.item_combo.currentIndex()}")
        ok("c7b377" not in tab._equipped_frames[1].styleSheet(), "old highlight cleared after switching selection")
        ok("c7b377" in tab._inv_frames[(0, 0)].styleSheet(), "newly selected cell highlighted")

        # clicking an empty cell does nothing
        before = tab.item_combo.currentIndex()
        tab._select_by_slot("inv", (2, 0))
        ok(tab.item_combo.currentIndex() == before, "clicking an empty cell does nothing")

        # clicking with no full_items does nothing and does not crash
        saved_full = tab.full_items
        tab.full_items = []
        tab._select_by_slot("equipped", 1)
        ok(tab.item_combo.currentIndex() == before, "cell click without full parse does nothing")
        tab.full_items = saved_full

        print("== UI save (Ctrl+S path) ==")
        win.save_file()
        save2 = load_d2s(win.save.path)
        ok(verify(save2), "after save, reloaded verify() checksum is True")
        ok(save2.path == dst, "saved to the temp copy (real save untouched)")
        ok(len(parse_item_list(bytes(save2.raw), save2.items.offset, version=save2.header.version)) == 67,
           "saved file parses all 67 items")
        print(f"\nUI smoke all passed: {_PASS} assertions, {len(shown)} dialog calls.")
    finally:
        win.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
