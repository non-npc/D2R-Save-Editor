"""符文转换行为自检: change_item_type 位流手术 + ItemsTab 符文转换控件。

全程在 sync/Amenda.d2s 的临时副本上操作, 绝不触碰 Saved Games 下的真实存档。
运行:
  python tests/test_rune_convert.py           (纯编解码部分)
  QT_QPA_PLATFORM=offscreen 环境 OK           (UI 部分自动跳过条件见下)
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


def span_end_of(items, idx: int):
    """物品实际占用跨度末尾 (= 下一顶层物品起始位; 尾部全零对齐字节随物品)。"""
    nxt = items[idx + 1] if idx + 1 < len(items) else None
    return nxt["_start_bit"] if nxt is not None else None

_PASS = 0


def ok(cond, msg: str) -> None:
    global _PASS
    assert cond, f"断言失败: {msg}"
    _PASS += 1
    print(f"  [通过] {msg}")


def make_tmp_save(tag: str):
    """复制存档到临时目录并加载 (测试完由调用方清理)。"""
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
    """位置签名: (location_id, equipped_id, alt_position_id, x, y) — 转换不得改变。"""
    return (it.get("location_id"), it.get("equipped_id"), it.get("alt_position_id"),
            it.get("position_x"), it.get("position_y"))


def items_sig(items: list) -> list:
    """全部物品的 (类型代码, 位置签名) 列表 — 往返转换后应逐件一致。"""
    return [((it.get("type") or "").strip(), loc_sig(it)) for it in items]


def save_and_verify(save, tag: str):
    save_d2s(save, path=save.path, make_backup=False)
    save2 = load_d2s(save.path)
    ok(verify(save2), f"[{tag}] save_d2s 后重新加载 verify() 校验和为 True")


# ---------------------------------------------------------------------------


def test_i18n_rune_coverage():
    print("== i18n: r01-r33 中文覆盖 ==")
    items = load_i18n().get("items", {})
    missing = [c for c in sorted(RUNE_EN_NAMES) if not items.get(c)]
    ok(not missing, f"r01-r33 全部有中文名 (缺失: {missing or '无'})")
    ok(len(RUNE_EN_NAMES) == 33, f"代码表 33 项 (实际 {len(RUNE_EN_NAMES)})")
    ok(items.get("r07") == "塔尔符文" and items.get("r33") == "萨德符文",
       f"r07={items.get('r07')!r} r33={items.get('r33')!r}")
    # 基础物品表也能解析 r07 / r33 (类型代码必须真实存在于游戏数据)
    constants = load_constants()
    for code in ("r07", "r33"):
        found = any(code in constants[t] for t in ("armor_items", "weapon_items", "other_items"))
        ok(found, f"{code} 在基础物品表中存在 (可解析可写回)")


def test_convert_r07_to_r33():
    print("== 转换: 储物处 Tal Rune (r07) -> Zod (r33) ==")
    save, tmp = make_tmp_save("to33")
    try:
        items = reparse(save)
        ok(len(items) == 67, f"基线解析 67 件物品 (实际 {len(items)})")
        idx, rune = find_rune(items, "r07")
        ok(rune is not None, f"找到 Tal Rune (r07) 样本, 索引 {idx}")
        ok(rune.get("simple_item") == 1, "符文是简单物品 (simple_item==1, 支持类型更换)")
        loc_before = loc_sig(rune)
        sig_before = items_sig(items)
        span_end = span_end_of(items, idx)
        ok(span_end is not None and span_end - rune["_end_bit"] == 8,
           f"符文尾部有全零对齐/堆叠字节 (span_end - _end_bit = {span_end - rune['_end_bit']})")
        raw_before = bytes(save.raw)
        n_before = len(save.raw)

        change_item_type(save.raw, rune, "r33", span_end=span_end)

        ok(len(save.raw) == n_before, f"变长转换 (r07 20位 -> r33 21位) 文件长度不变 ({n_before})")
        ok(bytes(save.raw[span_end // 8:]) == raw_before[span_end // 8:],
           "物品跨度之后的字节逐字节不变 (其余物品未受影响)")
        items2 = reparse(save)
        ok(len(items2) == 67, "转换后 67 件物品仍完整解析 (物品数不变)")
        idx2, rune2 = find_rune(items2, "r33")
        ok(idx2 == idx and rune2 is not None, f"重新解析读回类型 'r33' (同一索引 {idx2})")
        ok(loc_sig(rune2) == loc_before, f"位置保持不变: {loc_sig(rune2)}")
        title = describe_item(rune2)["title"]
        ok("萨德" in title, f"中文标题显示符文名: {title!r}")
        ok(all((it.get("type") or "").strip() != "r07" for it in items2), "原 r07 已不存在")
        sig_after = list(items_sig(items2))
        sig_after[idx2] = sig_before[idx]  # 目标物品自身已是 r33
        ok(sig_after == sig_before, "转换后其余 66 件物品类型/位置逐件一致")
        save_and_verify(save, "r07->r33")

        # 往返: r33 -> r07, 应精确还原原始字节流
        items3 = reparse(save)
        _, rune3 = find_rune(items3, "r33")
        change_item_type(save.raw, rune3, "r07", span_end=span_end_of(items3, idx))
        items4 = reparse(save)
        _, rune4 = find_rune(items4, "r07")
        ok(rune4 is not None and loc_sig(rune4) == loc_before, "转回 'r07': 类型与位置一致")
        ok(items_sig(items4) == sig_before, "往返转换后全部 67 件物品类型/位置与基线逐件一致")
        save_and_verify(save, "r33->r07")
        # 内容还原后 save_d2s 重算的校验和与原文件一致 -> 整个文件逐字节还原
        ok(bytes(save.raw) == raw_before, "往返转换并保存后整个文件与原始逐字节一致")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_roundtrip_byte_identity():
    print("== 字节还原: 等霍夫曼位长的目标码 (r07<->r09, 均为20位) 往返 ==")
    save, tmp = make_tmp_save("identity")
    try:
        items = reparse(save)
        idx, rune = find_rune(items, "r07")
        ok(rune is not None, "找到 Tal Rune (r07)")
        n07 = len(encode_type_code("r07 "))
        n09 = len(encode_type_code("r09 "))
        ok(n07 == n09, f"r07/r09 类型码位长相等 ({n07} == {n09}, 字节还原可行)")
        raw_before = bytes(save.raw)
        change_item_type(save.raw, rune, "r09", span_end=span_end_of(reparse(save), idx))
        items2 = reparse(save)
        idx2, rune2 = find_rune(items2, "r09")
        ok(idx2 == idx and rune2 is not None, "读回类型 'r09' (同一索引)")
        change_item_type(save.raw, rune2, "r07", span_end=span_end_of(items2, idx))
        items3 = reparse(save)
        ok(find_rune(items3, "r07")[0] == idx, "转回 'r07'")
        ok(bytes(save.raw) == raw_before, "等位长往返转换后字节流与原始完全一致")
        save_and_verify(save, "r09往返")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sweep_all_33_codes():
    print("== 全量: r07 依次转为 r01..r33 共 33 个目标码, 再转回 ==")
    save, tmp = make_tmp_save("sweep")
    try:
        items = reparse(save)
        idx, rune = find_rune(items, "r07")
        ok(rune is not None, "找到 Tal Rune (r07)")
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
            ok(len(save.raw) == n_before, f"-> {code} 文件长度不变")
            cur = find_rune(items2, code)[1]
            ok(cur is not None and loc_sig(cur) == loc_before,
               f"-> {code} ({RUNE_EN_NAMES[code]}) 读回并保持位置")
        items3 = reparse(save)
        change_item_type(save.raw, find_rune(items3, "r33")[1], "r07",
                         span_end=span_end_of(items3, idx))
        back = find_rune(reparse(save), "r07")[1]
        ok(back is not None, "转回 r07")
        ok(items_sig(reparse(save)) == sig_before, "33 次转换后全部物品类型/位置与基线逐件一致")
        ok(bytes(save.raw) == raw_before, "33 次转换后整个文件字节流与原始完全一致")
        save_and_verify(save, "sweep")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_reject_invalid():
    print("== 拒绝: 非简单物品 / 非法类型码 ==")
    save, tmp = make_tmp_save("reject")
    try:
        items = reparse(save)
        helm = next(it for it in items if it.get("type") == "hlm")
        ok(helm.get("simple_item") != 1, "头盔是非简单物品 (advanced)")
        try:
            change_item_type(save.raw, helm, "r33")
            ok(False, "非简单物品应抛 ValueError")
        except ValueError:
            ok(True, "非简单物品抛 ValueError (拒绝)")
        _, rune = find_rune(items, "r07")
        try:
            change_item_type(save.raw, rune, "r@@")
            ok(False, "非法类型码应抛 ValueError")
        except ValueError:
            ok(True, "非法类型码 (无法霍夫曼编码) 抛 ValueError")
        # 变长但无尾部填充字节可抵扣 (span_end 传 _end_bit) -> 拒绝, 存档未动
        raw_before = bytes(save.raw)
        try:
            change_item_type(save.raw, rune, "r04", span_end=rune["_end_bit"])  # 20->23 位
            ok(False, "无填充字节时变长转换应抛 ValueError")
        except ValueError:
            ok(True, "无全零填充可抵扣时变长转换抛 ValueError (拒绝)")
        try:
            change_item_type(save.raw, rune, "r05", span_end=0)  # 跨度异常
            ok(False, "跨度异常应抛 ValueError")
        except ValueError:
            ok(True, "span_end 异常 (0) 抛 ValueError (拒绝)")
        ok(bytes(save.raw) == raw_before, "拒绝路径不改动任何字节")
        ok(find_rune(reparse(save), "r07")[1] is not None, "拒绝后存档未损坏 (r07 仍可解析)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ui_rune_convert():
    print("== UI: 符文转换控件 (offscreen, 弹窗打桩) ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from app.main import MainWindow
    except Exception as e:  # pragma: no cover
        print(f"  [跳过] PyQt6 不可用: {e}")
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
        ok(combo.count() == 34, f"符文下拉框 34 项 (33 符文 + 占位, 实际 {combo.count()})")
        ok(combo.itemText(0) == "选择目标符文…" and combo.itemData(0) is None,
           f"占位项显示 {combo.itemText(0)!r} 且 itemData=None")
        i_r33 = next(i for i in range(combo.count()) if combo.itemData(i) == "r33")
        i_r07 = next(i for i in range(combo.count()) if combo.itemData(i) == "r07")
        ok("萨德符文 (Zod)" == combo.itemText(i_r33), f"r33 项显示 {combo.itemText(i_r33)!r}")
        ok("塔尔符文 (Tal)" == combo.itemText(i_r07), f"r07 项显示 {combo.itemText(i_r07)!r}")
        ok(not tab.rune_convert_btn.isEnabled() and not combo.isEnabled(),
           "初始 (非符文物品) 控件组禁用")

        idx, _ = find_rune(tab.full_items, "r07")
        ok(idx >= 0, f"full_items 中找到 r07 (索引 {idx})")
        tab.item_combo.setCurrentIndex(idx)  # 触发 _show_props
        ok(tab.rune_convert_btn.isEnabled() and combo.isEnabled(),
           "选中符文后控件组启用")
        # 占位项点击转换 -> 提示且不改动
        tab.rune_convert_btn.click()
        ok("info" in shown, "占位项 (未选目标) 点击转换弹出提示")
        ok(win.dirty is False, "未选目标时不标记 dirty")
        ok(find_rune(reparse(win.save), "r07")[0] == idx, "未选目标时物品未变")

        # 真实转换: r07 -> r33
        combo.setCurrentIndex(i_r33)
        tab.rune_convert_btn.click()
        ok(win.dirty, "转换后标记 dirty")
        items2 = reparse(win.save)
        idx2, rune2 = find_rune(items2, "r33")
        ok(idx2 == idx and rune2 is not None, f"重新解析读回类型 'r33' (同一索引 {idx2})")
        ok("萨德" in tab.item_combo.itemText(idx), f"物品下拉框文字已更新: {tab.item_combo.itemText(idx)!r}")
        ok(combo.currentIndex() == 0, "转换成功后下拉框复位到占位项")
        ok(tab.rune_convert_btn.isEnabled(), "转换后仍是符文, 控件组保持启用")

        # 转回 r07 (往返)
        combo.setCurrentIndex(i_r07)
        tab.rune_convert_btn.click()
        items3 = reparse(win.save)
        ok(find_rune(items3, "r07")[0] == idx, "转回 'r07': 重新解析读回类型")
        ok(find_rune(items3, "r33")[0] == -1, "r33 已不存在")
        save_and_verify(win.save, "UI往返")

        # 格子刷新: 把转换后的物品临时视为背包格 (3,2), _populate_cells 应显示新符文名
        it = tab.full_items[idx]
        it["location_id"], it["alt_position_id"] = 0, 1
        it["position_x"], it["position_y"] = 3, 2
        tab._populate_cells()
        lbl = tab.inv_cells[(3, 2)]
        ok("符文" in lbl.text(), f"背包格 (3,2) 刷新显示: {lbl.text()!r}")

        # 切回非符文物品 -> 控件组禁用
        tab.item_combo.setCurrentIndex(10)
        ok(not tab.rune_convert_btn.isEnabled() and not combo.isEnabled(),
           "切到非符文物品后控件组禁用")
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
    print(f"\n符文转换自检全部通过: {_PASS} 条断言, 0 失败。")


if __name__ == "__main__":
    main()
