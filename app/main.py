from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path so 'd2s' package can be found
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QAction, QKeySequence, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFileDialog, QMessageBox, QFormLayout, QLineEdit, QSpinBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QStatusBar,
    QGroupBox, QGridLayout, QCheckBox, QComboBox, QTextEdit, QSizePolicy,
    QFrame, QScrollArea, QInputDialog
)

from app.settings_dialog import SettingsDialog

from d2s.io import load_d2s, save_d2s, verify
from d2s.header import CLASS_NAMES, class_name, apply_header_edits, parse_header, set_filesize
from d2s.checksum import write_checksum
from d2s.template import get_template_bytes
from d2s.skills import write_skills
from d2s.quests import set_quest_completed, set_prison_of_ice_scroll, DIFFS as QUEST_DIFFS
from d2s.waypoints import WAYPOINTS, set_waypoint, DIFFS as WP_DIFFS
from d2s.items import set_simple_item_flag_bits
from d2s.stats import set_stat, ATTR_NAMES, ATTR_BITS
from d2s.skill_names import get_skill_name, skill_id_for_slot
from d2s.item_names import get_item_name, get_item_location, EQUIPPED_NAMES
from d2s.diagnostics import find_markers, find_fourcc_tags

from d2s.models import SaveFile, QuestEntry, ItemSimpleHeader

APP_TITLE = "D2R Save Editor"

def _mono_font() -> QFont:
    f = QFont("Consolas")
    if not f.exactMatch():
        f = QFont("Courier New")
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f

class OverviewTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.form = QFormLayout()
        self.setLayout(self.form)

        self.lbl_sig = QLabel("-")
        self.lbl_ver = QLabel("-")
        self.lbl_size = QLabel("-")
        self.lbl_checksum = QLabel("-")
        self.lbl_checksum_ok = QLabel("-")

        self.edit_name = QLineEdit()
        self.edit_name.setMaximumWidth(180)
        self.spin_level = QSpinBox()
        self.spin_level.setRange(1, 99)
        self.spin_level.setMaximumWidth(80)

        self.lbl_class = QLabel("-")
        self.lbl_flags = QLabel("-")
        self.lbl_note = QLabel("")

        self.form.addRow("Signature", self.lbl_sig)
        self.form.addRow("Version", self.lbl_ver)
        self.form.addRow("File size", self.lbl_size)
        self.form.addRow("Checksum (stored)", self.lbl_checksum)
        self.form.addRow("Checksum valid?", self.lbl_checksum_ok)
        self.form.addRow("Name", self.edit_name)
        self.form.addRow("Class", self.lbl_class)
        self.form.addRow("Level", self.spin_level)
        self.form.addRow("Flags (legacy)", self.lbl_flags)
        self.form.addRow("Note", self.lbl_note)

class SkillsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.info = QLabel("Skills block not loaded.")
        self.table = QTableWidget(30, 2)
        self.table.setHorizontalHeaderLabels(["Skill", "Value"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)

        for r in range(30):
            it = QTableWidgetItem(str(r))  # placeholder, updated in _refresh_ui
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, it)
            self.table.setItem(r, 1, QTableWidgetItem("0"))

        layout.addWidget(self.info)
        layout.addWidget(self.table)

    def set_enabled(self, enabled: bool, msg: str = ""):
        self.table.setEnabled(enabled)
        self.info.setText(msg)

class QuestsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout()
        self.setLayout(root)

        header = QHBoxLayout()
        self.diff = QComboBox()
        self.diff.addItems(QUEST_DIFFS)
        header.addWidget(QLabel("Difficulty:"))
        header.addWidget(self.diff)
        header.addStretch(1)

        self.info = QLabel("Quests not loaded.")
        root.addLayout(header)
        root.addWidget(self.info)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Act", "Quest", "Completed", "Special"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        root.addWidget(self.table)

        self.diff.currentIndexChanged.connect(self._rebuild)
        self._save_ref: SaveFile | None = None

    def bind(self, save: SaveFile | None):
        self._save_ref = save
        self._rebuild()

    def _rebuild(self):
        save = self._save_ref
        if not save or not save.quests:
            self.info.setText('Quests marker "Woo!" not found; quests editing disabled.')
            self.table.setRowCount(0)
            self.table.setEnabled(False)
            return

        self.table.setEnabled(True)
        dname = self.diff.currentText()
        entries = save.quests.difficulties.get(dname, [])
        self.table.setRowCount(len(entries))
        self.info.setText('Quest data loaded via marker "Woo!". Completed toggles bit 0; Prison of Ice has a special bit.')

        for r, e in enumerate(entries):
            self.table.setItem(r, 0, QTableWidgetItem(f"Act {e.act}"))
            self.table.setItem(r, 1, QTableWidgetItem(e.name))

            chk = QCheckBox()
            chk.setChecked(bool(e.value & 1))
            chk.stateChanged.connect(lambda state, ent=e: self._toggle_completed(ent, state == Qt.CheckState.Checked.value))
            self.table.setCellWidget(r, 2, chk)

            special_widget = QWidget()
            sp_l = QHBoxLayout()
            sp_l.setContentsMargins(0, 0, 0, 0)
            special_widget.setLayout(sp_l)
            if e.act == 5 and e.index_in_act == 2:
                sp = QCheckBox("Scroll consumed")
                sp.setChecked(bool((e.value >> 7) & 1))
                sp.stateChanged.connect(lambda state, ent=e: self._toggle_scroll(ent, state == Qt.CheckState.Checked.value))
                sp_l.addWidget(sp)
            else:
                sp_l.addWidget(QLabel("-"))
            sp_l.addStretch(1)
            self.table.setCellWidget(r, 3, special_widget)

        self.table.resizeColumnsToContents()

    def _toggle_completed(self, ent: QuestEntry, completed: bool):
        save = self._save_ref
        if not save:
            return
        set_quest_completed(save.raw, ent, completed)
        ent.value = int.from_bytes(save.raw[ent.offset:ent.offset+2], "little")
        self.parent().parent()._mark_dirty()

    def _toggle_scroll(self, ent: QuestEntry, consumed: bool):
        save = self._save_ref
        if not save:
            return
        set_prison_of_ice_scroll(save.raw, ent, consumed)
        ent.value = int.from_bytes(save.raw[ent.offset:ent.offset+2], "little")
        self.parent().parent()._mark_dirty()

class WaypointsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout()
        self.setLayout(root)

        header = QHBoxLayout()
        self.diff = QComboBox()
        self.diff.addItems(WP_DIFFS)
        header.addWidget(QLabel("Difficulty:"))
        header.addWidget(self.diff)
        header.addStretch(1)

        self.info = QLabel("Waypoints not loaded.")
        self.info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        root.addLayout(header)
        root.addWidget(self.info)

        box = QGroupBox("Waypoints")
        grid = QGridLayout()
        box.setLayout(grid)
        root.addWidget(box)

        self.checks: list[QCheckBox] = []
        cols = 3
        for i, name in enumerate(WAYPOINTS):
            cb = QCheckBox(f"{i:02d} — {name}")
            self.checks.append(cb)
            r = i // cols
            c = i % cols
            grid.addWidget(cb, r, c)
            cb.stateChanged.connect(lambda state, idx=i: self._toggle(idx, state == Qt.CheckState.Checked.value))

        root.addWidget(box)
        root.addStretch(1)
        self.diff.currentIndexChanged.connect(self._populate)
        self._save_ref: SaveFile | None = None

    def bind(self, save: SaveFile | None):
        self._save_ref = save
        self._populate()

    def _populate(self):
        save = self._save_ref
        if not save or not save.waypoints:
            self.info.setText('Waypoint marker "WS" not found; waypoint editing disabled.')
            for cb in self.checks:
                cb.setEnabled(False)
                cb.setChecked(False)
            return

        self.info.setText('Waypoints loaded via marker "WS". 39-bit bitfield (LSB order).')
        diff = self.diff.currentText()
        bitfield = save.waypoints.difficulties.get(diff, 1)

        for i, cb in enumerate(self.checks):
            cb.blockSignals(True)
            cb.setEnabled(True)
            cb.setChecked(bool((bitfield >> i) & 1))
            cb.blockSignals(False)

    def _toggle(self, idx: int, enabled: bool):
        save = self._save_ref
        if not save or not save.waypoints:
            return
        diff = self.diff.currentText()
        set_waypoint(save.raw, save.waypoints, diff, idx, enabled)
        self.parent().parent()._mark_dirty()

class StatsTab(QWidget):
    """Editable character stats: Strength, Dexterity, Vitality, Energy, Gold, etc."""
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout()
        self.setLayout(root)

        self.info = QLabel("Stats block not loaded.")
        self.info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        root.addWidget(self.info)

        self.spins: dict[int, QSpinBox] = {}

        # Core attributes: Strength, Energy, Dexterity, Vitality
        core_box = QGroupBox("Core Attributes")
        core_form = QFormLayout()
        for stat_id in (0, 1, 2, 3):
            name = ATTR_NAMES.get(stat_id, f"Stat {stat_id}")
            bits = ATTR_BITS.get(stat_id, 10)
            spin = self._make_spin(bits)
            self.spins[stat_id] = spin
            core_form.addRow(name, spin)
        core_box.setLayout(core_form)
        root.addWidget(core_box)

        # Life, Mana, Stamina
        life_box = QGroupBox("Life / Mana / Stamina")
        life_form = QFormLayout()
        for stat_id in (6, 7, 8, 9, 10, 11):
            name = ATTR_NAMES.get(stat_id, f"Stat {stat_id}")
            bits = ATTR_BITS.get(stat_id, 21)
            spin = self._make_spin(bits)
            self.spins[stat_id] = spin
            life_form.addRow(name, spin)
        life_box.setLayout(life_form)
        root.addWidget(life_box)

        # Level, Experience, Gold
        misc_box = QGroupBox("Level / Experience / Gold")
        misc_form = QFormLayout()
        for stat_id in (12, 13, 14, 15):
            name = ATTR_NAMES.get(stat_id, f"Stat {stat_id}")
            bits = ATTR_BITS.get(stat_id, 32)
            spin = self._make_spin(bits)
            self.spins[stat_id] = spin
            misc_form.addRow(name, spin)
        misc_box.setLayout(misc_form)
        root.addWidget(misc_box)
        root.addStretch(1)

        self._save_ref: SaveFile | None = None

    def _make_spin(self, bits: int) -> QSpinBox:
        max_val = min((1 << bits) - 1, 2147483647)  # QSpinBox max is signed 32-bit
        spin = QSpinBox()
        spin.setRange(0, max_val)
        spin.setSpecialValueText("")
        spin.setMaximumWidth(100)
        spin.valueChanged.connect(lambda *a: self.window()._mark_dirty())
        return spin

    def bind(self, save: SaveFile | None):
        self._save_ref = save
        self._populate()

    def _populate(self):
        save = self._save_ref
        if not save or not save.stats:
            self.info.setText('Stats marker "gf" not found; stats editing disabled.')
            for spin in self.spins.values():
                spin.setEnabled(False)
                spin.setValue(0)
            return

        self.info.setText('Stats loaded via marker "gf". Edit values and save.')
        for stat_id, spin in self.spins.items():
            ent = save.stats.entries.get(stat_id)
            if ent is not None:
                spin.setEnabled(True)
                spin.blockSignals(True)
                spin.setValue(ent.value)
                spin.blockSignals(False)
            else:
                spin.setEnabled(False)
                spin.setValue(0)

    def collect_values(self) -> dict[int, int]:
        """Return stat_id -> value for all enabled spins that have a valid entry in save."""
        save = self._save_ref
        if not save or not save.stats:
            return {}
        out = {}
        for stat_id, spin in self.spins.items():
            if spin.isEnabled() and stat_id in save.stats.entries:
                out[stat_id] = spin.value()
        return out

def _make_slot_frame(slot_name: str) -> tuple[QFrame, QLabel]:
    """Create a slot frame with label for equipped/inventory display."""
    frame = QFrame()
    frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
    frame.setMinimumSize(72, 48)
    frame.setStyleSheet("QFrame { background-color: #2d2d2d; }")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(4, 2, 4, 2)
    lbl_name = QLabel(slot_name)
    lbl_name.setStyleSheet("color: #888; font-size: 9px;")
    layout.addWidget(lbl_name)
    lbl_item = QLabel("—")
    lbl_item.setWordWrap(True)
    lbl_item.setStyleSheet("font-size: 10px;")
    layout.addWidget(lbl_item, 1)
    return frame, lbl_item


class ItemsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout()
        self.setLayout(root)

        self.info = QLabel("Items not loaded.")
        root.addWidget(self.info)

        content = QHBoxLayout()
        # Left: Equipped (paperdoll)
        equipped_group = QGroupBox("Equipped")
        equipped_layout = QGridLayout()
        self.equipped_slots: dict[int, QLabel] = {}
        slot_order = [(1, 0, 0), (2, 0, 1), (3, 0, 2), (4, 1, 0), (5, 1, 2), (6, 2, 0), (7, 2, 2), (8, 2, 1), (9, 3, 1), (10, 3, 0), (11, 4, 0), (12, 4, 2)]
        for slot_id, row, col in slot_order:
            name = EQUIPPED_NAMES.get(slot_id, f"Slot {slot_id}")
            frame, lbl = _make_slot_frame(name)
            equipped_layout.addWidget(frame, row, col)
            self.equipped_slots[slot_id] = lbl
        equipped_group.setLayout(equipped_layout)
        content.addWidget(equipped_group)

        # Right: Inventory (10x4 grid)
        inv_group = QGroupBox("Inventory")
        inv_layout = QGridLayout()
        self.inv_cells: dict[tuple[int, int], QLabel] = {}
        for r in range(4):
            for c in range(10):
                frame, lbl = _make_slot_frame(f"c{c},r{r}")
                inv_layout.addWidget(frame, r, c)
                self.inv_cells[(c, r)] = lbl
        inv_group.setLayout(inv_layout)
        content.addWidget(inv_group, 1)

        root.addLayout(content)

        # Raw list (collapsible)
        self.raw_group = QGroupBox("All items (raw)")
        self.raw_table = QTableWidget(0, 5)
        self.raw_table.setHorizontalHeaderLabels(["#", "Type", "Location", "Flags", "Note"])
        self.raw_table.verticalHeader().setVisible(False)
        self.raw_group.setLayout(QVBoxLayout())
        self.raw_group.layout().addWidget(self.raw_table)
        root.addWidget(self.raw_group)

        self._save_ref: SaveFile | None = None

    def bind(self, save: SaveFile | None):
        self._save_ref = save
        self._populate()

    def _populate(self):
        save = self._save_ref
        if not save or not save.items:
            self.info.setText('Items marker "JM" not found; items disabled.')
            self._clear_slots()
            self.raw_table.setRowCount(0)
            return
        items = save.items
        msg = f'Item list at 0x{items.offset:X}: {items.count} items, parsed {len(items.parsed)}.'
        if items.stopped_on_advanced:
            msg += " (Stopped on advanced item.)"
        self.info.setText(msg)

        # Clear slots
        for lbl in self.equipped_slots.values():
            lbl.setText("—")
        for lbl in self.inv_cells.values():
            lbl.setText("—")

        # Place items
        for it in items.parsed:
            name = get_item_name(it.type_code)
            if it.identified:
                pass
            else:
                name = f"{name} (unid)"
            if it.parent == 1 and it.equipped and it.equipped in self.equipped_slots:
                self.equipped_slots[it.equipped].setText(name)
            elif it.parent == 0 and it.stash == 1:
                c, r = it.column, it.row
                if (c, r) in self.inv_cells:
                    existing = self.inv_cells[(c, r)].text()
                    if existing != "—":
                        self.inv_cells[(c, r)].setText(f"{existing}\n{name}")
                    else:
                        self.inv_cells[(c, r)].setText(name)

        # Raw table
        self.raw_table.setRowCount(len(items.parsed))
        for r, it in enumerate(items.parsed):
            self.raw_table.setItem(r, 0, QTableWidgetItem(str(r)))
            self.raw_table.setItem(r, 1, QTableWidgetItem(get_item_name(it.type_code)))
            loc = get_item_location(it.parent, it.equipped, it.stash, it.column, it.row)
            self.raw_table.setItem(r, 2, QTableWidgetItem(loc))
            flags = []
            if it.identified: flags.append("ID")
            if it.socketed: flags.append("Sock")
            if it.ethereal: flags.append("Eth")
            self.raw_table.setItem(r, 3, QTableWidgetItem(", ".join(flags) or "—"))
            self.raw_table.setItem(r, 4, QTableWidgetItem("advanced" if it.advanced else "simple"))
        self.raw_table.resizeColumnsToContents()

    def _clear_slots(self):
        for lbl in self.equipped_slots.values():
            lbl.setText("—")
        for lbl in self.inv_cells.values():
            lbl.setText("—")

    def _set_item(self, item: ItemSimpleHeader, **kwargs):
        save = self._save_ref
        if not save or not save.items or item.advanced:
            return
        set_simple_item_flag_bits(save.raw, item, **kwargs)
        self.parent().parent()._mark_dirty()

class DiagnosticsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout()
        self.setLayout(root)

        self.summary = QLabel("Open a file to view diagnostics.")
        root.addWidget(self.summary)

        tables = QHBoxLayout()
        root.addLayout(tables)

        self.tbl_markers = QTableWidget(0, 2)
        self.tbl_markers.setHorizontalHeaderLabels(["Marker", "Offset"])
        self.tbl_markers.verticalHeader().setVisible(False)
        self.tbl_markers.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_markers.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tables.addWidget(self.tbl_markers)

        self.tbl_tags = QTableWidget(0, 3)
        self.tbl_tags.setHorizontalHeaderLabels(["Tag", "Offset", "Preview"])
        self.tbl_tags.verticalHeader().setVisible(False)
        self.tbl_tags.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_tags.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tables.addWidget(self.tbl_tags)

        self.hexview = QTextEdit()
        self.hexview.setReadOnly(True)
        self.hexview.setFont(_mono_font())
        root.addWidget(QLabel("Hex dump (first 2048 bytes):"))
        root.addWidget(self.hexview)

    def bind(self, save: SaveFile | None):
        if not save:
            self.summary.setText("Open a file to view diagnostics.")
            self.tbl_markers.setRowCount(0)
            self.tbl_tags.setRowCount(0)
            self.hexview.setPlainText("")
            return

        raw = bytes(save.raw)
        markers = find_markers(raw)
        tags = find_fourcc_tags(raw, scan_max=4096)

        self.summary.setText(
            f"Version: 0x{save.header.version:X} ({save.header.version}) | "
            f"Name offset: 0x{save.header.name_offset:X} | "
            f"Class: {class_name(save.header.char_class)} | "
            f"Markers found: {len(markers)} | Tags found (heuristic): {len(tags)}"
        )

        self.tbl_markers.setRowCount(len(markers))
        for r, h in enumerate(markers):
            self.tbl_markers.setItem(r, 0, QTableWidgetItem(h.name))
            self.tbl_markers.setItem(r, 1, QTableWidgetItem(f"0x{h.offset:X} ({h.offset})"))
        self.tbl_markers.resizeColumnsToContents()

        self.tbl_tags.setRowCount(len(tags))
        for r, t in enumerate(tags):
            off = t.offset
            preview = raw[off:off+32]
            prev_hex = " ".join(f"{b:02X}" for b in preview)
            self.tbl_tags.setItem(r, 0, QTableWidgetItem(repr(t.tag)))
            self.tbl_tags.setItem(r, 1, QTableWidgetItem(f"0x{off:X} ({off})"))
            self.tbl_tags.setItem(r, 2, QTableWidgetItem(prev_hex))
        self.tbl_tags.resizeColumnsToContents()

        # Hex dump first 2048
        dump_len = min(2048, len(raw))
        lines = []
        for i in range(0, dump_len, 16):
            chunk = raw[i:i+16]
            hx = " ".join(f"{b:02X}" for b in chunk)
            asc = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
            lines.append(f"{i:08X}  {hx:<47}  |{asc}|")
        self.hexview.setPlainText("\n".join(lines))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(900, 720)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())

        self.save: SaveFile | None = None
        self.dirty = False
        self._populating = False

        self.tabs = QTabWidget()
        self.overview = OverviewTab()
        self.stats_tab = StatsTab()
        self.skills = SkillsTab()
        self.quests = QuestsTab()
        self.waypoints = WaypointsTab()
        self.items = ItemsTab()
        self.diag = DiagnosticsTab()

        self.tabs.addTab(self.overview, "Overview")
        self.tabs.addTab(self.stats_tab, "Stats")
        self.tabs.addTab(self.skills, "Skills")
        self.tabs.addTab(self.quests, "Quests")
        self.tabs.addTab(self.waypoints, "Waypoints")
        self.tabs.addTab(self.items, "Items (partial)")
        self.tabs.addTab(self.diag, "Diagnostics")
        self.tabs.setTabEnabled(self.tabs.indexOf(self.items), False)
        self.setCentralWidget(self.tabs)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        act_open = QAction("Open…", self)
        act_open.triggered.connect(self.open_file)
        act_generate = QAction("Generate new Character…", self)
        act_generate.triggered.connect(self.generate_new_savefile)
        act_save = QAction("Save", self)
        act_save.setShortcut(QKeySequence(QKeySequence.StandardKey.Save))
        act_save.triggered.connect(self.save_file)
        act_saveas = QAction("Save As…", self)
        act_saveas.setShortcut(QKeySequence(QKeySequence.StandardKey.SaveAs))
        act_saveas.triggered.connect(self.save_as)
        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self.close)

        m = self.menuBar().addMenu("File")
        m.addAction(act_open)
        m.addAction(act_generate)
        m.addSeparator()
        m.addAction(act_save)
        m.addAction(act_saveas)
        self.addAction(act_save)
        self.addAction(act_saveas)
        m.addSeparator()
        m.addAction(act_exit)

        act_settings = QAction("Settings…", self)
        act_settings.triggered.connect(self._show_settings)
        m_settings = self.menuBar().addMenu("Settings")
        m_settings.addAction(act_settings)

        self.overview.edit_name.textEdited.connect(self._mark_dirty)
        self.overview.spin_level.valueChanged.connect(self._on_overview_level_changed)
        self.stats_tab.spins[12].valueChanged.connect(self._on_stats_level_changed)
        self.skills.table.itemChanged.connect(self._mark_dirty)

        self._refresh_ui()

    def _show_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def _mark_dirty(self, *args):
        if self.save is None or self._populating:
            return
        self.dirty = True
        self._update_status()

    def _on_overview_level_changed(self, value: int):
        if self._populating or self.save is None:
            return
        spin = self.stats_tab.spins.get(12)
        if spin is not None and spin.isEnabled():
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._mark_dirty()

    def _on_stats_level_changed(self, value: int):
        if self._populating or self.save is None:
            return
        if self.overview.spin_level.isEnabled():
            self.overview.spin_level.blockSignals(True)
            self.overview.spin_level.setValue(value)
            self.overview.spin_level.blockSignals(False)
        self._mark_dirty()

    def _update_status(self):
        path = self.save.path if self.save else "(no file)"
        chk = "-" if not self.save else ("OK" if verify(self.save) else "INVALID")
        dirt = " *modified*" if self.dirty else ""
        self.status.showMessage(f"{path}  | checksum: {chk}{dirt}")

    def _refresh_ui(self):
        self._populating = True
        try:
            if not self.save:
                self.overview.lbl_sig.setText("-")
                self.overview.lbl_ver.setText("-")
                self.overview.lbl_size.setText("-")
                self.overview.lbl_checksum.setText("-")
                self.overview.lbl_checksum_ok.setText("-")
                self.overview.edit_name.setText("")
                self.overview.spin_level.setValue(1)
                self.overview.spin_level.setEnabled(False)
                self.overview.lbl_class.setText("-")
                self.overview.lbl_flags.setText("-")
                self.overview.lbl_note.setText("Open a .d2s file to begin.")
                self.skills.set_enabled(False, "Open a file to load skills.")
                self.stats_tab.bind(None)
                self.quests.bind(None)
                self.waypoints.bind(None)
                self.items.bind(None)
                self.diag.bind(None)
                self._update_status()
                return

            hdr = self.save.header
            self.overview.lbl_sig.setText(hex(hdr.signature))
            self.overview.lbl_ver.setText(str(hdr.version))
            self.overview.lbl_size.setText(str(hdr.file_size))
            self.overview.lbl_checksum.setText(hex(hdr.checksum))
            self.overview.lbl_checksum_ok.setText("YES" if verify(self.save) else "NO")
            self.overview.edit_name.setText(hdr.name)

            self.overview.lbl_class.setText(class_name(hdr.char_class))

            if hdr.level is None:
                self.overview.spin_level.setValue(1)
                self.overview.spin_level.setEnabled(False)
            else:
                self.overview.spin_level.setEnabled(True)
                self.overview.spin_level.setValue(int(hdr.level))

            flags = []
            if hdr.status is not None:
                if hdr.status & (1 << 2): flags.append("Hardcore")
                if hdr.status & (1 << 5): flags.append("Expansion")
            self.overview.lbl_flags.setText(", ".join(flags) if flags else "(n/a)")

            note = f"Name offset: 0x{hdr.name_offset:X}. "
            if hdr.level is None:
                note += "Level/class offsets unknown for this version; level editing disabled."
            elif hdr.level_offset is not None:
                note += "Level edit is enabled (legacy layout)."
            else:
                note += "Level from stats block; level editing enabled."
            self.overview.lbl_note.setText(note)

            if self.save.skills is None:
                self.skills.set_enabled(False, 'Skills marker "if" not found; skills editing disabled.')
            else:
                self.skills.set_enabled(True, 'Skills loaded via marker "if" (30 bytes).')
                char_class = self.save.header.char_class
                for r, val in enumerate(self.save.skills.values):
                    skill_id = skill_id_for_slot(char_class, r)
                    name = get_skill_name(skill_id) if skill_id is not None else f"Skill {r}"
                    self.skills.table.item(r, 0).setText(f"{r}: {name}")
                    self.skills.table.item(r, 1).setText(str(int(val)))

            self.stats_tab.bind(self.save)
            self.quests.bind(self.save)
            self.waypoints.bind(self.save)
            self.items.bind(self.save)
            self.diag.bind(self.save)

        finally:
            self._populating = False
            self._update_status()

    def maybe_discard_changes(self) -> bool:
        if not self.dirty:
            return True
        resp = QMessageBox.question(
            self, "Unsaved changes", "You have unsaved changes. Discard them?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resp == QMessageBox.StandardButton.Yes

    def open_file(self):
        if not self.maybe_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open .d2s", "", "D2 Saves (*.d2s);;All files (*.*)")
        if not path:
            return
        try:
            self.save = load_d2s(path)
            self.dirty = False
            self._refresh_ui()
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            self.save = None
            self.dirty = False
            self._refresh_ui()

    def _apply_ui_to_model(self):
        if not self.save:
            return

        name = self.overview.edit_name.text().strip()
        collected = self.stats_tab.collect_values()
        # Use Stats tab Level (stat 12) when available, else Overview - both can be edited
        level_val = collected.get(12, int(self.overview.spin_level.value()))

        # Always update stat 12 (Level) when stats block exists - D2R uses stats as canonical source
        if self.save.stats is not None and 12 in self.save.stats.entries:
            set_stat(self.save.raw, self.save.stats, 12, level_val)
            self.save.stats.entries[12].value = level_val

        # Update header (name, level - must match stats per d2s format)
        if self.save.header.level_offset is not None:
            apply_header_edits(self.save.raw, self.save.header, name=name, level=level_val)
        else:
            apply_header_edits(self.save.raw, self.save.header, name=name, level=None)
            # D2R (0x69+): level at 0x1B even when parse_header didn't find valid byte there
            if self.save.header.version >= 0x69 and len(self.save.raw) > 0x1B and 1 <= level_val <= 99:
                self.save.raw[0x1B] = level_val

        # Apply stats from Stats tab (use collected value for stat 12 - respects Stats tab edits)
        if self.save.stats is not None:
            for stat_id, value in collected.items():
                set_stat(self.save.raw, self.save.stats, stat_id, value)
                self.save.stats.entries[stat_id].value = value

        if self.save.skills is not None:
            vals = []
            for r in range(30):
                txt = self.skills.table.item(r, 1).text().strip()
                v = int(txt)
                if not (0 <= v <= 255):
                    raise ValueError(f"Skill value at row {r} must be 0..255.")
                vals.append(v)
            self.save.skills.values = vals
            write_skills(self.save.raw, self.save.skills)

        self.save.header = parse_header(self.save.raw)

    def generate_new_savefile(self):
        if not self.maybe_discard_changes():
            return
        template = get_template_bytes()
        if not template:
            QMessageBox.critical(
                self,
                "Template not found",
                "No template save file available.\n\n"
                "Place Brutus.d2s in d2s/data/ or run:\n"
                "  python tools/embed_brutus.py [path/to/Brutus.d2s]"
            )
            return

        name, ok = QInputDialog.getText(
            self,
            "Generate new Character",
            "Character name (used for save file name and character):\n"
            "Letters only (A–Z, a–z), 2–15 characters.",
            QLineEdit.EchoMode.Normal,
            "NewChar",
        )
        if not ok or not name or not name.strip():
            return

        name = name.strip()
        if not (2 <= len(name) <= 15):
            QMessageBox.critical(
                self, "Invalid name",
                "Name must be 2–15 characters."
            )
            return
        if not name.isalpha():
            QMessageBox.critical(
                self, "Invalid name",
                "Character name can only contain letters (A–Z, a–z).\n"
                "No spaces, digits, or special characters."
            )
            return

        class_list = [CLASS_NAMES[i] for i in range(len(CLASS_NAMES))]
        selected_class, ok = QInputDialog.getItem(
            self,
            "Generate new Character",
            "Select character class:",
            class_list,
            0,
            False,
        )
        if not ok:
            return
        char_class_id = class_list.index(selected_class)

        out, _ = QFileDialog.getSaveFileName(
            self,
            "Save new character",
            f"{name}.d2s",
            "D2 Saves (*.d2s);;All files (*.*)",
        )
        if not out:
            return
        if not out.lower().endswith(".d2s"):
            out += ".d2s"

        try:
            data = bytearray(template)
            hdr = parse_header(data)
            # Replace template name and class with user selections
            apply_header_edits(data, hdr, name=name, char_class=char_class_id)
            set_filesize(data)
            write_checksum(data)
            with open(out, "wb") as f:
                f.write(data)
            self.save = load_d2s(out)
            self.dirty = False
            self._refresh_ui()
            self._update_status()
            QMessageBox.information(
                self,
                "Save file created",
                f"Created {out}\n\nThe new character is now loaded in the editor.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Generate failed", str(e))

    def save_file(self):
        if not self.save:
            return
        try:
            self._apply_ui_to_model()
            save_d2s(self.save, path=self.save.path, make_backup=True)
            self.save = load_d2s(self.save.path)
            self.dirty = False
            self._refresh_ui()
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def save_as(self):
        if not self.save:
            return
        out, _ = QFileDialog.getSaveFileName(self, "Save As", "", "D2 Saves (*.d2s);;All files (*.*)")
        if not out:
            return
        if not out.lower().endswith(".d2s"):
            out += ".d2s"
        try:
            self._apply_ui_to_model()
            save_d2s(self.save, path=out, make_backup=False)
            self.save = load_d2s(out)
            self.dirty = False
            self._refresh_ui()
        except Exception as e:
            QMessageBox.critical(self, "Save As failed", str(e))

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
