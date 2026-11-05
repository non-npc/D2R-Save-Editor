"""UI 冒烟测试 (offscreen): 主窗口绑定存档副本, 词缀增删走真实 UI 代码路径。

运行: QT_QPA_PLATFORM=offscreen python tests/test_ui_smoke.py
全程在临时副本上操作, 不触碰 Saved Games 下的真实存档。
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
from d2s.item_codec import list_addable_props, parse_item_list
from app.main import MainWindow, affix_fields_spec, make_skill_combo

from _save_source import ensure_test_save, test_save_path
SRC_SAVE = ensure_test_save()
_PASS = 0


def ok(cond, msg: str) -> None:
    global _PASS
    assert cond, f"断言失败: {msg}"
    _PASS += 1
    print(f"  [通过] {msg}")


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

    # 静默模态弹窗 (记录调用即可)
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
        print("== 主窗口绑定 ==")
        ok(win.tabs.isTabEnabled(win.tabs.indexOf(tab)), "物品编辑页已启用")
        ok(tab.item_combo.count() == 67, f"物品下拉框 67 项 (实际 {tab.item_combo.count()})")
        ok(tab.props_table.columnCount() == 5, "词缀表 5 列 (含操作列)")

        print("== 选中头盔并查看词缀 ==")
        tab.item_combo.setCurrentIndex(10)
        tab._show_props(10)
        ok(tab.props_table.rowCount() >= 2, f"头盔词缀行数 {tab.props_table.rowCount()} >= 2")
        del_btns = [tab.props_table.cellWidget(r, 4) for r in range(tab.props_table.rowCount())
                    if tab.props_table.cellWidget(r, 4) is not None]
        ok(len(del_btns) >= 2, f"每条词缀行都有删除按钮 ({len(del_btns)} 个)")

        print("== 技能下拉框 ==")
        combo = make_skill_combo()
        ok(combo.count() == 429, f"技能下拉 429 项 (实际 {combo.count()})")
        hit = [i for i in range(combo.count()) if "微暗灵视" in combo.itemText(i)]
        ok(bool(hit) and combo.itemData(hit[0]) == 71, f"搜索到 '微暗灵视' -> 技能id {combo.itemData(hit[0])}")

        print("== 添加对话框参数显隐 ==")
        props = list_addable_props()
        dlg, c, vs, w = tab._build_affix_dialog("冒烟测试", props)
        i204 = next(i for i in range(c.count()) if c.itemData(i)["id"] == 204)
        c.setCurrentIndex(i204)
        ok(not w["lbl_cur"].isHidden(), "聚气词缀显示 当前次数 输入")
        ok(not w["max_spin"].isHidden(), "聚气词缀显示 最大次数 输入")
        ok(w["lbl_tab"].isHidden(), "聚气词缀不显示 技能页 输入")
        i195 = next(i for i in range(c.count()) if c.itemData(i)["id"] == 195)
        c.setCurrentIndex(i195)
        ok(not w["level_spin"].isHidden(), "触发词缀显示 技能等级 输入")
        ok(w["lbl_cur"].isHidden(), "触发词缀不显示 次数 输入")
        ok("概率" in w["lbl_value"].text(), f"触发词缀数值标签 = {w['lbl_value'].text()!r}")
        i7 = next(i for i in range(c.count()) if c.itemData(i)["id"] == 7)
        c.setCurrentIndex(i7)
        ok(w["skill_combo"].isHidden() and not w["value_spin"].isHidden(), "纯数值词缀只显示数值输入")
        dlg.deleteLater()

        print("== UI 添加聚气词缀 (_do_add_affix) ==")
        p204 = next(p for p in props if p["id"] == 204)
        spec = affix_fields_spec(p204, skill_id=71, level=5, cur=18, mx=25)
        tab._do_add_affix(win.save, 10, p204, spec)
        ok(win.dirty, "添加后标记 dirty")
        row = find_row_with_text(tab, 0, "微暗灵视")
        ok(row >= 0, f"词缀表出现新词缀行 (第 {row} 行)")
        ok("18/25" in tab.props_table.item(row, 0).text(), f"行文本含充能数: {tab.props_table.item(row, 0).text()!r}")
        items = parse_item_list(bytes(win.save.raw), win.save.items.offset, version=win.save.header.version)
        ok(len(items) == 67, "添加后 67 件物品仍完整解析")

        print("== UI 删除词缀 (删除按钮点击) ==")
        btn = tab.props_table.cellWidget(row, 4)
        ok(btn is not None, "新词缀行有删除按钮")
        btn.click()
        ok("question" in shown, "删除前弹出确认框")
        row_after = find_row_with_text(tab, 0, "微暗灵视")
        ok(row_after < 0, "删除后词缀行消失")
        items2 = parse_item_list(bytes(win.save.raw), win.save.items.offset, version=win.save.header.version)
        helm = items2[10]
        ok(all(p["id"] != 204 for p in helm["magic_attributes"]), "头盔词缀表中聚气词缀已删除")
        ok(len(items2) == 67, "删除后 67 件物品仍完整解析")

        print("== UI 添加技能词缀 (singleskill) ==")
        p107 = next(p for p in props if p["id"] == 107)
        spec = affix_fields_spec(p107, skill_id=373, value=2)
        tab._do_add_affix(win.save, 10, p107, spec)
        row = find_row_with_text(tab, 0, "召唤羊头人")
        ok(row >= 0, "词缀表出现 +2 至召唤羊头人")
        items3 = parse_item_list(bytes(win.save.raw), win.save.items.offset, version=win.save.header.version)
        p = items3[10]["magic_attributes"][-1]
        ok(p["id"] == 107 and p["fields"][0]["param"] == 373 and p["fields"][0]["value"] == 2,
           "重新解析读回 id/param/value 一致")

        print("== 格子显示与点击选择 ==")
        # 完整解析填充: 身上装备格显示中文物品名 (full_items[10] = 头盔, equipped_id=1)
        helm_lbl = tab.equipped_slots[1]
        ok("头盔" in helm_lbl.text(), f"头盔格显示中文物品名: {helm_lbl.text()!r}")
        book_lbl = tab.inv_cells[(0, 0)]
        ok("城镇传送之书" in book_lbl.text() and "×27" in book_lbl.text(),
           f"背包格(0,0)显示物品名与数量: {book_lbl.text()!r}")
        empty_lbl = tab.inv_cells[(2, 0)]
        ok(empty_lbl.text() == "—", "背包空格子仍显示占位符")

        # 模拟点击处理函数: 头盔格 → 下拉框指向索引 10
        tab._select_by_slot("equipped", 1)
        ok(tab.item_combo.currentIndex() == 10,
           f"点击头盔格 → 下拉框索引 {tab.item_combo.currentIndex()}")
        ok(tab.props_table.rowCount() > 0, "点击格子后词缀表行数 > 0")
        ok("c7b377" in tab._equipped_frames[1].styleSheet(), "选中格子边框高亮")

        # 真实鼠标点击背包格 (0,0) 城镇传送之书 (full_items 索引 64)
        QTest.mouseClick(tab.inv_cells[(0, 0)], Qt.MouseButton.LeftButton)
        ok(tab.item_combo.currentIndex() == 64,
           f"鼠标点击背包格 → 下拉框索引 {tab.item_combo.currentIndex()}")
        ok("c7b377" not in tab._equipped_frames[1].styleSheet(), "切换选择后旧高亮清除")
        ok("c7b377" in tab._inv_frames[(0, 0)].styleSheet(), "新选中格子高亮")

        # 空格子点击无反应
        before = tab.item_combo.currentIndex()
        tab._select_by_slot("inv", (2, 0))
        ok(tab.item_combo.currentIndex() == before, "点击空格子无反应")

        # 无 full_items 时点击无反应且不崩溃
        saved_full = tab.full_items
        tab.full_items = []
        tab._select_by_slot("equipped", 1)
        ok(tab.item_combo.currentIndex() == before, "无完整解析时点击格子无反应")
        tab.full_items = saved_full

        print("== UI 保存 (Ctrl+S 路径) ==")
        win.save_file()
        save2 = load_d2s(win.save.path)
        ok(verify(save2), "保存后重新加载 verify() 校验和为 True")
        ok(save2.path == dst, "保存路径为临时副本 (未触碰真实存档)")
        ok(len(parse_item_list(bytes(save2.raw), save2.items.offset, version=save2.header.version)) == 67,
           "保存后的文件 67 件物品完整解析")
        print(f"\nUI 冒烟全部通过: {_PASS} 条断言, 弹窗调用 {len(shown)} 次。")
    finally:
        win.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
