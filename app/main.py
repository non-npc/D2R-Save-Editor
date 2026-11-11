from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Add project root to path so 'd2s' package can be found
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QAction, QKeySequence, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFileDialog, QMessageBox, QFormLayout, QLineEdit, QSpinBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QStatusBar,
    QGroupBox, QGridLayout, QCheckBox, QComboBox, QTextEdit, QSizePolicy,
    QFrame, QScrollArea, QInputDialog, QDialog, QDialogButtonBox, QPushButton
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
from d2s.item_codec import (
    parse_item_list, describe_item, describe_magic_prop, patch_magic_value,
    add_magic_prop_ex, delete_magic_prop, list_addable_props,
    load_constants, load_i18n, gem_tiers, change_item_type,
)
from d2s.stats import set_stat, ATTR_NAMES, ATTR_BITS

from d2s.skill_names import get_skill_name, skill_id_for_slot
from d2s.item_names import get_item_name, get_item_location, EQUIPPED_NAMES
from d2s.diagnostics import find_markers, find_fourcc_tags

from d2s.models import SaveFile, QuestEntry, ItemSimpleHeader

APP_TITLE = "D2R Save Editor"


def tr(key: str, fallback: str | None = None) -> str:
    """Translate a UI label through the runtime-loaded language table.

    Looks up `key` in the "ui" section of the generated table
    (d2s/data/i18n_zh.json, built by tools/build_i18n.py from the user's own
    game strings). Returns the localized text on a hit, otherwise the English
    `fallback` (or the key itself when no fallback is given). Code contains
    only English keys and English fallbacks; all zh strings live in the
    generated table, so the codebase stays English-only.
    """
    ui = load_i18n().get("ui") or {}
    value = ui.get(key)
    if value:
        return value
    return fallback if fallback is not None else key

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About D2R Save Editor")
        layout = QVBoxLayout(self)
        lbl = QLabel(
            '<p><b>D2R Save Editor</b></p>'
            '<p>Created by non-npc</p>'
            '<p><a href="https://github.com/non-npc/D2R-Save-Editor">https://github.com/non-npc/D2R-Save-Editor</a></p>'
        )
        lbl.setOpenExternalLinks(True)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn.accepted.connect(self.accept)
        layout.addWidget(btn)

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

        self.form.addRow(tr("lbl_signature", "Signature"), self.lbl_sig)
        self.form.addRow(tr("lbl_version", "Version"), self.lbl_ver)
        self.form.addRow(tr("lbl_file_size", "File size"), self.lbl_size)
        self.form.addRow(tr("lbl_checksum_stored", "Checksum (stored)"), self.lbl_checksum)
        self.form.addRow(tr("lbl_checksum_valid", "Checksum valid?"), self.lbl_checksum_ok)
        self.form.addRow(tr("lbl_name", "Name"), self.edit_name)
        self.form.addRow(tr("lbl_class", "Class"), self.lbl_class)
        self.form.addRow(tr("lbl_level", "Level"), self.spin_level)
        self.form.addRow(tr("lbl_legacy_flags", "Legacy flags"), self.lbl_flags)
        self.form.addRow(tr("lbl_note", "Note"), self.lbl_note)

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
        self.window()._mark_dirty()

    def _toggle_scroll(self, ent: QuestEntry, consumed: bool):
        save = self._save_ref
        if not save:
            return
        set_prison_of_ice_scroll(save.raw, ent, consumed)
        ent.value = int.from_bytes(save.raw[ent.offset:ent.offset+2], "little")
        self.window()._mark_dirty()

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
        self.window()._mark_dirty()

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
        core_box = QGroupBox(tr("group_core_stats", "Core attributes"))
        core_form = QFormLayout()
        for stat_id in (0, 1, 2, 3):
            name = tr(f"stat_{stat_id}", ATTR_NAMES.get(stat_id, f"Stat {stat_id}"))
            bits = ATTR_BITS.get(stat_id, 10)
            spin = self._make_spin(bits)
            self.spins[stat_id] = spin
            core_form.addRow(name, spin)
        core_box.setLayout(core_form)
        root.addWidget(core_box)

        # Life, Mana, Stamina
        life_box = QGroupBox(tr("group_life_mana", "Life / Mana / Stamina"))
        life_form = QFormLayout()
        for stat_id in (6, 7, 8, 9, 10, 11):
            name = tr(f"stat_{stat_id}", ATTR_NAMES.get(stat_id, f"Stat {stat_id}"))
            bits = ATTR_BITS.get(stat_id, 21)
            spin = self._make_spin(bits)
            self.spins[stat_id] = spin
            life_form.addRow(name, spin)
        life_box.setLayout(life_form)
        root.addWidget(life_box)

        # Level, Experience, Gold
        misc_box = QGroupBox(tr("group_level_exp_gold", "Level / Experience / Gold"))
        misc_form = QFormLayout()
        for stat_id in (12, 13, 14, 15):
            name = tr(f"stat_{stat_id}", ATTR_NAMES.get(stat_id, f"Stat {stat_id}"))
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

class ClickableLabel(QLabel):
    """Clickable QLabel: emits `clicked` on left-button press (used for the
    item cell selection interaction)."""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# Item quality text colors (matching classic D2R palette: unique/rare/magic/set...)
QUALITY_COLORS = {
    1: "#9d9d9d",   # low quality (gray)
    3: "#d0d0d0",   # superior
    4: "#6969ff",   # magic (blue)
    5: "#00ff00",   # set (green)
    6: "#ffff80",   # rare (yellow)
    7: "#c7b377",   # unique/legendary (gold)
    8: "#ffa500",   # crafted (orange)
}

# Cell frame styles: the objectName selector only matches the frame itself so
# the inner QLabel (also a QFrame subclass) does not inherit border/background.
_SLOT_FRAME_STYLE = "#slotFrame { background-color: #2d2d2d; }"
_SLOT_FRAME_SELECTED_STYLE = "#slotFrame { background-color: #45402a; border: 3px solid #c7b377; }"


def _make_slot_frame(slot_name: str) -> tuple[QFrame, ClickableLabel]:
    """Create a slot frame with clickable label for equipped/inventory display."""
    frame = QFrame()
    frame.setObjectName("slotFrame")
    frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
    frame.setMinimumSize(72, 48)
    frame.setStyleSheet(_SLOT_FRAME_STYLE)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(4, 2, 4, 2)
    lbl_name = QLabel(slot_name)
    lbl_name.setStyleSheet("color: #888; font-size: 9px;")
    layout.addWidget(lbl_name)
    lbl_item = ClickableLabel("—")
    lbl_item.setWordWrap(True)
    lbl_item.setStyleSheet("font-size: 10px;")
    lbl_item.setCursor(Qt.CursorShape.PointingHandCursor)
    layout.addWidget(lbl_item, 1)
    return frame, lbl_item


def class_label(class_id: int) -> str:
    """Class display name: zh-CN from the language table when present, else
    the English class name. Valid ids are 0-6 only (7 is not a real class)."""
    return tr(f"class_{class_id}", CLASS_NAMES.get(class_id, f"Class {class_id}"))


# Parametric prop kinds -> dropdown hint labels (English fallbacks)
PARAM_KIND_LABELS = {
    "skill": "Select skill", "class": "Select class", "tab_skill": "Skill tab + skill",
    "cast": "Chance + level + skill", "charges": "Level + skill + charges",
}


# Runes r01-r33: type code -> original English name (#1-33, El..Zod). zh-CN
# names come from the i18n items table (build_i18n.py RUNE_NAMES_ZH) at
# runtime; one-way mapping, saves are written with the type code only.
RUNE_EN_NAMES = {
    "r01": "El", "r02": "Eld", "r03": "Tir", "r04": "Nef", "r05": "Eth",
    "r06": "Ith", "r07": "Tal", "r08": "Ral", "r09": "Ort", "r10": "Thul",
    "r11": "Amn", "r12": "Sol", "r13": "Shael", "r14": "Dol", "r15": "Hel",
    "r16": "Io", "r17": "Lum", "r18": "Ko", "r19": "Fal", "r20": "Lem",
    "r21": "Pul", "r22": "Um", "r23": "Mal", "r24": "Ist", "r25": "Gul",
    "r26": "Vex", "r27": "Ohm", "r28": "Lo", "r29": "Sur", "r30": "Ber",
    "r31": "Jah", "r32": "Cham", "r33": "Zod",
}
RUNE_CODE_RE = re.compile(r"^r\d{2}$")


def make_skill_combo(parent=None) -> QComboBox:
    """Skill dropdown: all 429 entries from skills_by_id (mod skills included),
    zh names via the language table when present (English otherwise), searchable
    by typed keyword (QCompleter contains-match). itemData = skill id."""
    constants = load_constants()
    i18n = load_i18n()
    by_id = i18n.get("skills_by_id", {})
    skills = constants.get("skills") or []
    combo = QComboBox(parent)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    for sid in sorted(int(k) for k in by_id):
        zh = by_id.get(str(sid))
        en = ""
        if sid < len(skills) and skills[sid]:
            en = skills[sid].get("s") or skills[sid].get("n") or ""
        label = f"{sid}: {zh or en or f'Skill {sid}'}"
        if en and zh and en.lower() != zh.lower():
            label += f" ({en})"
        combo.addItem(label, sid)
    completer = combo.completer()
    if completer is not None:
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    combo.setMaxVisibleItems(24)
    combo.setCurrentIndex(0)
    return combo


def affix_fields_spec(prop: dict, *, value: int = 0, skill_id: int | None = None,
                      tab: int = 0, class_id: int = 0, level: int = 0,
                      cur: int = 0, mx: int = 0) -> list:
    """UI inputs -> fields_spec for add_magic_prop_ex, dispatched by param_kind:
      skill: [(skill id, value)]         class: [(class id, value)]
      tab_skill: [((skill tab, skill id), value)]
      cast: [((level, skill id), chance %)]
      charges: [((level, skill id), (current, max) charges)]"""
    kind = prop.get("param_kind")
    if kind is None:
        return [(None, int(value))]
    if skill_id is None and kind != "class":
        raise ValueError("Please select a skill")
    if kind == "skill":
        return [(int(skill_id), int(value))]
    if kind == "class":
        return [(int(class_id), int(value))]
    if kind == "tab_skill":
        return [((int(tab), int(skill_id)), int(value))]
    if kind == "cast":
        return [((int(level), int(skill_id)), int(value))]
    if kind == "charges":
        return [((int(level), int(skill_id)), (int(cur), int(mx)))]
    raise ValueError(f"Unsupported parametric prop kind: {kind}")


class ItemsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout()
        self.setLayout(root)

        self.info = QLabel("Items not loaded.")
        root.addWidget(self.info)

        content = QHBoxLayout()
        # Left: Equipped (paperdoll)
        equipped_group = QGroupBox(tr("group_equipped", "Equipped"))
        equipped_layout = QGridLayout()
        self.equipped_slots: dict[int, ClickableLabel] = {}
        self._equipped_frames: dict[int, QFrame] = {}
        slot_order = [(1, 0, 0), (2, 0, 1), (3, 0, 2), (4, 1, 0), (5, 1, 2), (6, 2, 0), (7, 2, 2), (8, 2, 1), (9, 3, 1), (10, 3, 0), (11, 4, 0), (12, 4, 2)]
        for slot_id, row, col in slot_order:
            name = EQUIPPED_NAMES.get(slot_id, f"Slot {slot_id}")
            frame, lbl = _make_slot_frame(name)
            equipped_layout.addWidget(frame, row, col)
            self.equipped_slots[slot_id] = lbl
            self._equipped_frames[slot_id] = frame
            lbl.clicked.connect(lambda key=slot_id: self._select_by_slot("equipped", key))
        equipped_group.setLayout(equipped_layout)
        content.addWidget(equipped_group)

        # Right: Inventory (10x4 grid)
        inv_group = QGroupBox(tr("group_inventory", "Inventory"))
        inv_layout = QGridLayout()
        self.inv_cells: dict[tuple[int, int], ClickableLabel] = {}
        self._inv_frames: dict[tuple[int, int], QFrame] = {}
        for r in range(4):
            for c in range(10):
                frame, lbl = _make_slot_frame(f"c{c},r{r}")
                inv_layout.addWidget(frame, r, c)
                self.inv_cells[(c, r)] = lbl
                self._inv_frames[(c, r)] = frame
                lbl.clicked.connect(lambda key=(c, r): self._select_by_slot("inv", key))
        inv_group.setLayout(inv_layout)
        content.addWidget(inv_group, 1)

        root.addLayout(content)

        # Raw list (collapsible)
        self.raw_group = QGroupBox(tr("group_raw_list", "Item list (raw parse)"))
        self.raw_table = QTableWidget(0, 5)
        self.raw_table.setHorizontalHeaderLabels(["#", "Type", "Location", "Flags", "Note"])
        self.raw_table.verticalHeader().setVisible(False)
        self.raw_group.setLayout(QVBoxLayout())
        self.raw_group.layout().addWidget(self.raw_table)
        root.addWidget(self.raw_group)

        # Full-parse list + magic property editor
        self.detail_group = QGroupBox(tr("group_item_edit", "Item list / affix value editing"))
        detail_layout = QVBoxLayout()
        combo_row = QHBoxLayout()
        combo_row.addWidget(QLabel(tr("lbl_select_item", "Select item:")))
        self.item_combo = QComboBox()
        self.item_combo.currentIndexChanged.connect(self._show_props)
        combo_row.addWidget(self.item_combo, 1)
        detail_layout.addLayout(combo_row)
        tip = QLabel(tr("tip_click_cells", "Tip: click a cell above (Equipped / Inventory) to select that item and edit its affixes."))
        tip.setStyleSheet("color: #999; font-size: 11px;")
        detail_layout.addWidget(tip)

        self.props_table = QTableWidget(0, 5)
        self.props_table.setHorizontalHeaderLabels([
            tr("col_affix", "Affix"), tr("col_current", "Current"),
            tr("col_new", "New value"), tr("col_status", "Status"), tr("col_action", "Action"),
        ])
        self.props_table.horizontalHeader().setStretchLastSection(False)
        self.props_table.verticalHeader().setVisible(False)
        detail_layout.addWidget(self.props_table, 1)

        apply_row = QHBoxLayout()
        self.apply_btn = QPushButton(tr("btn_apply_affixes", "Apply affix value edits"))
        self.apply_btn.clicked.connect(self._apply_prop_edits)
        self.add_affix_btn = QPushButton(tr("btn_add_affix", "➕ Add affix"))
        self.add_affix_btn.clicked.connect(self._add_affix)
        self.gem_up_btn = QPushButton(tr("btn_gem_upgrade", "⬆ Upgrade gem tier"))
        self.gem_up_btn.clicked.connect(lambda: self._gem_step(False))
        self.gem_max_btn = QPushButton(tr("btn_gem_max", "⬆⬆ Upgrade gem to perfect"))
        self.gem_max_btn.clicked.connect(lambda: self._gem_step(True))
        self.gem_up_btn.setEnabled(False)
        self.gem_max_btn.setEnabled(False)
        # rune conversion controls: enabled when the selected item is a rune (r01-r33)
        self.rune_label = QLabel(tr("lbl_rune", "Rune:"))
        self.rune_combo = QComboBox()
        self.rune_combo.addItem(tr("rune_placeholder", "Select target rune…"), None)  # placeholder, avoids accidental triggers
        _rune_items = load_i18n().get("items", {})
        for _rc in sorted(RUNE_EN_NAMES):
            _zh = _rune_items.get(_rc)
            _label = f"{_zh} ({RUNE_EN_NAMES[_rc]})" if _zh else f"{RUNE_EN_NAMES[_rc]} ({_rc})"
            self.rune_combo.addItem(_label, _rc)  # itemData = type code (used for write-back)
        self.rune_convert_btn = QPushButton(tr("btn_rune_convert", "Convert to this rune"))
        self.rune_convert_btn.clicked.connect(self._rune_convert)
        for _w in (self.rune_label, self.rune_combo, self.rune_convert_btn):
            _w.setEnabled(False)
            apply_row.addWidget(_w)
        apply_row.addWidget(self.apply_btn)
        apply_row.addWidget(self.add_affix_btn)
        apply_row.addWidget(self.gem_up_btn)
        apply_row.addWidget(self.gem_max_btn)
        apply_row.addStretch(1)
        detail_layout.addLayout(apply_row)
        self.detail_group.setLayout(detail_layout)
        root.addWidget(self.detail_group, 1)

        self.full_items = []      # parsed item dicts (item_codec)
        self._prop_spins = []     # (field_dict, QSpinBox)
        self._shown_index = -1    # item index of the last _show_props (for rune placeholder reset)
        self._save_ref: SaveFile | None = None

    def bind(self, save: SaveFile | None):
        self._save_ref = save
        self.full_items = []
        if save and save.items:
            try:
                self.full_items = parse_item_list(
                    bytes(save.raw), save.items.offset, version=save.header.version
                )
            except Exception as e:
                self.full_items = []
                QMessageBox.warning(
                    self, tr("dlg_title_parse_warning", "Item parsing"),
                    tr("msg_parse_failed", "Full item parse failed (other features unaffected):\n{error}").format(error=e)
                )
        self._populate()

    def _flatten_item(self, it: dict, prefix: str = "") -> list[tuple[str, dict]]:
        """List of (display title, item dict), socketed items included."""
        out = [(prefix + describe_item(it)["title"], it)]
        for sub in it.get("socketed_items", []) or []:
            out.extend(self._flatten_item(sub, prefix + "  └ "))
        return out

    # ---- cell display and click selection ----

    def _find_index_for_slot(self, kind: str, key) -> int:
        """Locate the item index for a cell in full_items; -1 when not found.
        Equipped: location_id==1 and equipped_id matches;
        Inventory: location_id==0, alt_position_id==1 and position_x/y
        (column/row) match."""
        for i, it in enumerate(self.full_items):
            if kind == "equipped":
                if it.get("location_id") == 1 and it.get("equipped_id") == key:
                    return i
            else:  # inv
                if (it.get("location_id") == 0 and it.get("alt_position_id") == 1
                        and it.get("position_x") == key[0]
                        and it.get("position_y") == key[1]):
                    return i
        return -1

    def _clear_cell_highlight(self) -> None:
        """Restore the default border style on all cells."""
        for frame in self._equipped_frames.values():
            frame.setStyleSheet(_SLOT_FRAME_STYLE)
        for frame in self._inv_frames.values():
            frame.setStyleSheet(_SLOT_FRAME_STYLE)

    def _set_cell_highlight(self, kind: str, key) -> None:
        """Highlight the selected cell's border (clears other cells first)."""
        self._clear_cell_highlight()
        frames = self._equipped_frames if kind == "equipped" else self._inv_frames
        frame = frames.get(key)
        if frame is not None:
            frame.setStyleSheet(_SLOT_FRAME_SELECTED_STYLE)

    def _select_by_slot(self, kind: str, key) -> None:
        """Cell click -> move the "select item" combo to that item and show its
        affix table. No-op for empty cells or when full_items is empty."""
        if not self.full_items:
            return
        idx = self._find_index_for_slot(kind, key)
        if idx < 0:
            return
        self.item_combo.blockSignals(True)
        self.item_combo.setCurrentIndex(idx)
        self.item_combo.blockSignals(False)
        self._show_props(idx)
        self._set_cell_highlight(kind, key)

    def _show_props(self, index: int):
        self._clear_cell_highlight()
        self.props_table.setRowCount(0)
        self._prop_spins = []
        if not (0 <= index < len(self.full_items)):
            return
        flat = self._flatten_item(self.full_items[index])
        rows = []  # (display text, field, prop or None, owner item)
        HEADER_FIELDS = (
            ("_defense_field", tr("hdr_defense", "Defense")),
            ("_durmax_field", tr("hdr_max_durability", "Max Durability")),
            ("_durcur_field", tr("hdr_durability", "Durability")),
            ("_qty_field", tr("hdr_quantity", "Quantity")),
        )
        for title, it in flat:
            for key, label in HEADER_FIELDS:
                f = it.get(key)
                if f:
                    rows.append((f"{title} — {label}", f, None, it))
            for prop in it.get("magic_attributes", []) or []:
                for field in prop.get("fields", []):
                    label = describe_magic_prop(prop) if field is prop["fields"][0] else f"   ↳ {field['name']}"
                    rows.append((label, field, prop, it))
        self.props_table.setRowCount(len(rows))
        for r, (label, field, prop, owner) in enumerate(rows):
            name_item = QTableWidgetItem(label)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.props_table.setItem(r, 0, name_item)

            cur = QTableWidgetItem(str(field.get("value", "-")))
            cur.setFlags(cur.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.props_table.setItem(r, 1, cur)

            if field.get("editable"):
                bits = field.get("bits", 8)
                spin = QSpinBox()
                spin.setRange(0, (1 << bits) - 1)
                spin.setValue(field.get("value", 0))
                self.props_table.setCellWidget(r, 2, spin)
                self._prop_spins.append((field, spin))
                status = tr("status_editable", "editable")
            else:
                status_item = QTableWidgetItem(tr("status_special_readonly", "(special encoding, read-only)"))
                status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.props_table.setItem(r, 2, status_item)
                status = tr("status_readonly", "read-only")
            st = QTableWidgetItem(status)
            st.setFlags(st.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.props_table.setItem(r, 3, st)

            # action column: each affix (first row) gets a "delete" button
            if prop is not None and field is prop["fields"][0]:
                btn = QPushButton(tr("btn_delete", "Delete"))
                btn.setToolTip(tr("tooltip_delete_affix", "Delete this affix from the prop list (whole np group)"))
                btn.clicked.connect(lambda _=False, it=owner, p=prop: self._delete_affix(it, p))
                self.props_table.setCellWidget(r, 4, btn)
            else:
                dash = QTableWidgetItem("—")
                dash.setFlags(dash.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.props_table.setItem(r, 4, dash)
        self.props_table.resizeColumnToContents(0)
        self.props_table.resizeColumnToContents(4)
        # gem upgrade buttons: enabled when the selected item is a gem with a next tier
        try:
            if 0 <= index < len(self.full_items):
                t = (self.full_items[index].get("type") or "").strip()
                self.gem_up_btn.setEnabled(t in gem_tiers())
                self.gem_max_btn.setEnabled(t in gem_tiers())
            else:
                self.gem_up_btn.setEnabled(False)
                self.gem_max_btn.setEnabled(False)
        except Exception:
            self.gem_up_btn.setEnabled(False)
            self.gem_max_btn.setEnabled(False)
        # rune conversion controls: enabled when the selected item is a rune
        # (type code r01-r33); the placeholder is reset when switching to
        # another item (avoids accidental conversion with the previous item's target)
        is_rune = False
        if 0 <= index < len(self.full_items):
            is_rune = bool(RUNE_CODE_RE.match((self.full_items[index].get("type") or "").strip()))
        for w in (self.rune_label, self.rune_combo, self.rune_convert_btn):
            w.setEnabled(is_rune)
        if is_rune and self._shown_index != index:
            self.rune_combo.setCurrentIndex(0)
        self._shown_index = index

    def _gem_step(self, to_max: bool):
        save = self._save_ref
        idx = self.item_combo.currentIndex()
        if not save or not (0 <= idx < len(self.full_items)):
            return
        item = self.full_items[idx]
        t = (item.get("type") or "").strip()
        chains = gem_tiers()
        if t not in chains:
            QMessageBox.information(self, tr("dlg_title_info", "Info"),
                                    tr("msg_not_gem", "The selected item is not an upgradeable gem."))
            return
        new_type = chains[t]
        if to_max:
            guard = 0
            while new_type in chains and guard < 10:
                new_type = chains[new_type]
                guard += 1
        # growing tier upgrades need the item's trailing padding bytes: span_end = next item's start bit
        span_end = None
        if idx + 1 < len(self.full_items):
            nxt = self.full_items[idx + 1]
            if nxt.get("_start_bit") is not None:
                span_end = nxt["_start_bit"]
        try:
            change_item_type(save.raw, item, new_type, span_end=span_end)
        except ValueError as e:
            QMessageBox.critical(self, tr("dlg_title_upgrade_failed", "Upgrade failed"), str(e))
            return
        self.window()._mark_dirty()
        # bit offsets changed: re-parse and keep the selection
        self.full_items = parse_item_list(bytes(save.raw), save.items.offset, version=save.header.version)
        self.item_combo.blockSignals(True)
        self.item_combo.clear()
        for it in self.full_items:
            d = describe_item(it)
            self.item_combo.addItem(f"[{d['quality']}] {d['title']}")
        self.item_combo.setCurrentIndex(idx)
        self.item_combo.blockSignals(False)
        self._show_props(idx)
        QMessageBox.information(
            self, tr("dlg_title_upgrade_ok", "Upgrade successful"),
            tr("msg_upgrade_ok", "Gem upgraded to \"{title}\".\nPress Ctrl+S to save to file (automatic .bak backup).")
            .format(title=describe_item(self.full_items[idx])["title"])
        )

    def _rune_convert(self):
        """Convert the selected rune item to the target rune picked in the
        combo (r01-r33, any conversion, no tier restrictions). Same pattern as
        _gem_step: change_item_type bit surgery -> mark dirty -> re-parse
        keeping the selection -> refresh cell text -> success dialog."""
        save = self._save_ref
        idx = self.item_combo.currentIndex()
        if not save or not (0 <= idx < len(self.full_items)):
            return
        item = self.full_items[idx]
        t = (item.get("type") or "").strip()
        if not RUNE_CODE_RE.match(t):
            QMessageBox.information(self, tr("dlg_title_info", "Info"),
                                    tr("msg_not_rune", "The selected item is not a rune."))
            return
        new_type = self.rune_combo.currentData()
        if not new_type:
            QMessageBox.information(self, tr("dlg_title_info", "Info"),
                                    tr("msg_no_rune_target", "Pick a target rune in the combo first."))
            return
        # the span the item actually occupies (incl. trailing zero alignment /
        # stack bytes) = the next top-level item's start bit. Passing span_end
        # lets the type-code length change be absorbed inside the span: other
        # items' bytes stay untouched and growing conversions are in-game safe
        # (see the change_item_type docs).
        nxt = self.full_items[idx + 1] if idx + 1 < len(self.full_items) else None
        span_end = nxt.get("_start_bit") if nxt is not None else None
        try:
            change_item_type(save.raw, item, new_type, span_end=span_end)
        except ValueError as e:
            QMessageBox.critical(self, tr("dlg_title_convert_failed", "Conversion failed"), str(e))
            return
        self.window()._mark_dirty()
        # bit offsets changed: re-parse and keep the selection; refresh cell text too
        self.full_items = parse_item_list(bytes(save.raw), save.items.offset, version=save.header.version)
        self.item_combo.blockSignals(True)
        self.item_combo.clear()
        for it in self.full_items:
            d = describe_item(it)
            self.item_combo.addItem(f"[{d['quality']}] {d['title']}")
        self.item_combo.setCurrentIndex(idx)
        self.item_combo.blockSignals(False)
        self._show_props(idx)
        self.rune_combo.setCurrentIndex(0)  # placeholder reset, avoids accidental repeat clicks
        self._populate_cells()
        # when the item sits in an equipped/inventory cell, keep the cell highlighted
        it = self.full_items[idx]
        if it.get("location_id") == 1:
            self._set_cell_highlight("equipped", it.get("equipped_id"))
        elif it.get("location_id") == 0 and it.get("alt_position_id") == 1:
            self._set_cell_highlight("inv", (it.get("position_x"), it.get("position_y")))
        QMessageBox.information(
            self, tr("dlg_title_convert_ok", "Conversion successful"),
            tr("msg_convert_ok", "Item converted to \"{title}\".\nPress Ctrl+S to save to file (automatic .bak backup).")
            .format(title=describe_item(self.full_items[idx])["title"])
        )

    def _build_affix_dialog(self, title: str, props: list):
        """Build the "add affix" dialog. Returns (dlg, affix combo, value spin,
        param widget dict). Param widgets show/hide dynamically per the
        affix's param_kind."""
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("dlg_title_add_affix", "Add affix → {title}").format(title=title))
        dlg.resize(600, 340)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(tr("lbl_target_item", "Target item: {title}").format(title=title)))
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("lbl_affix", "Affix:")))
        combo = QComboBox()
        for p in props:
            label = p["desc"]
            if p.get("param_kind"):
                kind_lbl = PARAM_KIND_LABELS.get(p["param_kind"], p["param_kind"])
                label += f"   [{tr('param_hint', 'requires parameter')} {kind_lbl}]"
            combo.addItem(label, p)
        row.addWidget(combo, 1)
        v.addLayout(row)

        # parameter area (skill / level / skill tab / class / charges)
        grid = QGridLayout()
        w: dict = {}
        lbl_skill = QLabel(tr("lbl_skill", "Skill:"))
        w["skill_combo"] = make_skill_combo(dlg)
        lbl_level = QLabel(tr("lbl_skill_level", "Skill level:"))
        level_spin = QSpinBox()
        level_spin.setRange(0, 63)
        level_spin.setValue(1)
        w["level_spin"] = level_spin
        lbl_tab = QLabel(tr("lbl_skill_tab", "Skill tab (0-7):"))
        tab_spin = QSpinBox()
        tab_spin.setRange(0, 7)
        w["tab_spin"] = tab_spin
        lbl_class = QLabel(tr("lbl_class", "Class:"))
        class_combo = QComboBox()
        for cid in range(7):
            class_combo.addItem(f"{cid}: {class_label(cid)}", cid)
        w["class_combo"] = class_combo
        lbl_cur = QLabel(tr("lbl_cur_charges", "Current charges:"))
        cur_spin = QSpinBox()
        cur_spin.setRange(1, 255)
        cur_spin.setValue(1)
        w["cur_spin"] = cur_spin
        lbl_max = QLabel(tr("lbl_max_charges", "Max charges:"))
        max_spin = QSpinBox()
        max_spin.setRange(1, 255)
        max_spin.setValue(1)
        w["max_spin"] = max_spin
        for key, lbl in (("lbl_skill", lbl_skill), ("lbl_level", lbl_level),
                         ("lbl_tab", lbl_tab), ("lbl_class", lbl_class),
                         ("lbl_cur", lbl_cur), ("lbl_max", lbl_max)):
            w[key] = lbl
        grid.addWidget(lbl_skill, 0, 0)
        grid.addWidget(w["skill_combo"], 0, 1)
        grid.addWidget(lbl_level, 1, 0)
        grid.addWidget(level_spin, 1, 1)
        grid.addWidget(lbl_tab, 2, 0)
        grid.addWidget(tab_spin, 2, 1)
        grid.addWidget(lbl_class, 3, 0)
        grid.addWidget(class_combo, 3, 1)
        cur_max_row = QHBoxLayout()
        cur_max_row.addWidget(lbl_cur)
        cur_max_row.addWidget(cur_spin)
        cur_max_row.addWidget(lbl_max)
        cur_max_row.addWidget(max_spin)
        cur_max_row.addStretch(1)
        grid.addLayout(cur_max_row, 4, 0, 1, 2)
        v.addLayout(grid)

        # value area (chance / value)
        row2 = QHBoxLayout()
        lbl_value = QLabel(tr("lbl_value", "Value:"))
        w["lbl_value"] = lbl_value
        value_spin = QSpinBox()
        w["value_spin"] = value_spin
        row2.addWidget(lbl_value)
        row2.addWidget(value_spin)
        row2.addStretch(1)
        v.addLayout(row2)
        note = QLabel(tr("note_add_affix",
                         "Tip: skill-based affixes support keyword search; the affix is inserted "
                         "at the end of the item's prop list.\nThe original file is backed up as .bak on save."))
        v.addWidget(note)

        def on_prop_changed(i):
            p = combo.itemData(i)
            kind = p.get("param_kind")
            show = {
                "lbl_skill": kind in ("skill", "tab_skill", "cast", "charges"),
                "skill_combo": kind in ("skill", "tab_skill", "cast", "charges"),
                "lbl_level": kind in ("cast", "charges"),
                "level_spin": kind in ("cast", "charges"),
                "lbl_tab": kind == "tab_skill",
                "tab_spin": kind == "tab_skill",
                "lbl_class": kind == "class",
                "class_combo": kind == "class",
                "lbl_cur": kind == "charges",
                "cur_spin": kind == "charges",
                "lbl_max": kind == "charges",
                "max_spin": kind == "charges",
                "lbl_value": kind != "charges",
                "value_spin": kind != "charges",
            }
            for key, vis in show.items():
                w[key].setVisible(vis)
            if kind == "cast":
                lbl_value.setText(tr("lbl_chance", "Chance (%):"))
            else:
                lbl_value.setText(tr("lbl_value", "Value:"))
            lo, hi = (1, 255) if kind == "charges" else (p["min"], p["max"])
            value_spin.setRange(lo, hi)
            value_spin.setValue(min(max(1, lo), hi))
        combo.currentIndexChanged.connect(on_prop_changed)
        on_prop_changed(0)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        return dlg, combo, value_spin, w

    def _add_affix(self):
        save = self._save_ref
        idx = self.item_combo.currentIndex()
        if not save or not (0 <= idx < len(self.full_items)):
            QMessageBox.information(self, tr("dlg_title_info", "Info"),
                                    tr("msg_select_item_first", "Select an item above first."))
            return
        item = self.full_items[idx]
        title = describe_item(item)["title"]
        props = list_addable_props()
        dlg, combo, value_spin, w = self._build_affix_dialog(title, props)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        prop = combo.currentData()
        try:
            spec = affix_fields_spec(
                prop,
                value=value_spin.value(),
                skill_id=w["skill_combo"].currentData(),
                tab=w["tab_spin"].value(),
                class_id=w["class_combo"].currentData(),
                level=w["level_spin"].value(),
                cur=w["cur_spin"].value(),
                mx=w["max_spin"].value(),
            )
        except ValueError as e:
            QMessageBox.critical(self, tr("dlg_title_add_failed", "Add failed"), str(e))
            return
        self._do_add_affix(save, idx, prop, spec)

    def _do_add_affix(self, save, idx: int, prop: dict, spec: list):
        """Perform the affix insertion and refresh the UI (shared by the
        dialog and the tests)."""
        item = self.full_items[idx]
        title = describe_item(item)["title"]
        try:
            add_magic_prop_ex(save.raw, item, prop["id"], spec)
        except ValueError as e:
            QMessageBox.critical(self, tr("dlg_title_add_failed", "Add failed"), str(e))
            return
        self.window()._mark_dirty()
        self._reparse_refresh(idx)
        # after re-parsing the new prop sits at the end of the list; build the
        # display text from the parse result
        new_prop = self.full_items[idx]["magic_attributes"][-1]
        desc = describe_magic_prop(new_prop) if new_prop["id"] == prop["id"] else prop["desc"]
        QMessageBox.information(
            self, tr("dlg_title_add_ok", "Add successful"),
            tr("msg_add_ok", "Added to \"{title}\": {desc}\nPress Ctrl+S to save to file (automatic .bak backup).")
            .format(title=title, desc=desc)
        )

    def _delete_affix(self, owner_item: dict, prop: dict):
        """Delete one affix (whole np group), re-parse and refresh afterwards."""
        save = self._save_ref
        if not save:
            return
        desc = describe_magic_prop(prop)
        resp = QMessageBox.question(
            self, tr("dlg_title_delete_affix", "Delete affix"),
            tr("msg_delete_confirm", "Delete this affix from the item?\n\n{desc}").format(desc=desc),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        idx = self.item_combo.currentIndex()
        try:
            delete_magic_prop(save.raw, owner_item, prop)
        except ValueError as e:
            QMessageBox.critical(self, tr("dlg_title_delete_failed", "Delete failed"), str(e))
            return
        self.window()._mark_dirty()
        self._reparse_refresh(idx)
        QMessageBox.information(
            self, tr("dlg_title_delete_ok", "Delete successful"),
            tr("msg_delete_ok", "Deleted affix: {desc}\nPress Ctrl+S to save to file (automatic .bak backup).")
            .format(desc=desc)
        )

    def _reparse_refresh(self, idx: int):
        """After a bit-stream splice (insert/delete) all bit offsets change:
        re-parse and keep the selection."""
        save = self._save_ref
        self.full_items = parse_item_list(bytes(save.raw), save.items.offset, version=save.header.version)
        self.item_combo.blockSignals(True)
        self.item_combo.clear()
        for it in self.full_items:
            d = describe_item(it)
            self.item_combo.addItem(f"[{d['quality']}] {d['title']}")
        self.item_combo.setCurrentIndex(idx)
        self.item_combo.blockSignals(False)
        self._show_props(idx)

    def _apply_prop_edits(self):
        save = self._save_ref
        if not save:
            return
        changed = 0
        try:
            for field, spin in self._prop_spins:
                if not field.get("editable"):
                    continue
                new_val = spin.value()
                if new_val == field.get("value"):
                    continue
                patch_magic_value(save.raw, field, new_val)
                field["value"] = new_val
                changed += 1
        except ValueError as e:
            QMessageBox.critical(self, tr("dlg_title_edit_failed", "Edit failed"), str(e))
            return
        if changed:
            self.window()._mark_dirty()
            QMessageBox.information(
                self, tr("dlg_title_applied", "Applied"),
                tr("msg_apply_ok", "Modified {count} affix value(s) (in memory; press Ctrl+S to save to file).\n"
                   "The original file is backed up as .bak on save.")
                .format(count=changed)
            )
        else:
            QMessageBox.information(self, tr("dlg_title_no_changes", "No changes"),
                                    tr("msg_no_changes", "Nothing to apply."))

    def _populate_cells(self):
        """Clear and refill the Equipped / Inventory cells from full_items
        (item names / quality colors / stack counts). Shared by _populate and
        the post-conversion cell refresh (_populate additionally handles the
        fallback and the raw table)."""
        self._clear_slots()
        if not self.full_items:
            return
        for it in self.full_items:
            loc = it.get("location_id")
            if loc == 1:
                cells = self.equipped_slots
                key = it.get("equipped_id")
            elif loc == 0 and it.get("alt_position_id") == 1:
                cells = self.inv_cells
                key = (it.get("position_x"), it.get("position_y"))
            else:
                continue
            lbl = cells.get(key)
            if lbl is None or lbl.text() != "—":
                continue  # several items in one cell (stack): show the first only
            d = describe_item(it)
            title = d["title"]
            qty = it.get("quantity")
            if qty:
                title += f" ×{qty}"
            lbl.setText(title)
            lbl.setToolTip(f"[{d['quality']}] {title}")
            color = QUALITY_COLORS.get(it.get("quality"), "#e0e0e0")
            lbl.setStyleSheet(f"color: {color}; font-size: 10px;")

    def _populate(self):
        save = self._save_ref
        if not save or not save.items:
            self.info.setText('Items marker "JM" not found; items disabled.')
            self._clear_slots()
            self.raw_table.setRowCount(0)
            self.item_combo.clear()
            self.props_table.setRowCount(0)
            return
        items = save.items
        msg = f'Item list at 0x{items.offset:X}: {items.count} items, parsed {len(items.parsed)}.'
        if items.stopped_on_advanced:
            msg += " (Stopped on advanced item.)"
        self.info.setText(msg)

        # Clear slots + fill cells from the full parse (item names + quality colors + counts)
        self._populate_cells()

        if not self.full_items:
            # fallback: when the full parse is unavailable, show approximate
            # locations using the old simple parse
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

        # Full-parse combo (item dropdown)
        self.item_combo.blockSignals(True)
        self.item_combo.clear()
        for it in self.full_items:
            d = describe_item(it)
            self.item_combo.addItem(f"[{d['quality']}] {d['title']}")
        self.item_combo.blockSignals(False)
        if self.full_items:
            self._show_props(0)

    def _clear_slots(self):
        self._clear_cell_highlight()
        for lbl in self.equipped_slots.values():
            lbl.setText("—")
            lbl.setStyleSheet("font-size: 10px;")
            lbl.setToolTip("")
        for lbl in self.inv_cells.values():
            lbl.setText("—")
            lbl.setStyleSheet("font-size: 10px;")
            lbl.setToolTip("")

    def _set_item(self, item: ItemSimpleHeader, **kwargs):
        save = self._save_ref
        if not save or not save.items or item.advanced:
            return
        set_simple_item_flag_bits(save.raw, item, **kwargs)
        self.window()._mark_dirty()

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

        self.tabs.addTab(self.overview, tr("tab_overview", "Overview"))
        self.tabs.addTab(self.stats_tab, tr("tab_stats", "Stats"))
        self.tabs.addTab(self.skills, tr("tab_skills", "Skills"))
        self.tabs.addTab(self.quests, tr("tab_quests", "Quests"))
        self.tabs.addTab(self.waypoints, tr("tab_waypoints", "Waypoints"))
        self.tabs.addTab(self.items, tr("tab_items", "Items (edit)"))
        self.tabs.addTab(self.diag, tr("tab_diagnostics", "Diagnostics"))
        self.tabs.setTabEnabled(self.tabs.indexOf(self.items), False)
        self.setCentralWidget(self.tabs)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        act_open = QAction(tr("act_open_save", "Open save…"), self)
        act_open.triggered.connect(self.open_file)
        act_generate = QAction(tr("act_generate_character", "Generate new character…"), self)
        act_generate.triggered.connect(self.generate_new_savefile)
        act_save = QAction(tr("act_save", "Save"), self)
        act_save.setShortcut(QKeySequence(QKeySequence.StandardKey.Save))
        act_save.triggered.connect(self.save_file)
        act_saveas = QAction(tr("act_save_as", "Save As…"), self)
        act_saveas.setShortcut(QKeySequence(QKeySequence.StandardKey.SaveAs))
        act_saveas.triggered.connect(self.save_as)
        act_exit = QAction(tr("act_exit", "Exit"), self)
        act_exit.triggered.connect(self.close)

        m = self.menuBar().addMenu(tr("menu_file", "File"))
        m.addAction(act_open)
        m.addAction(act_generate)
        m.addSeparator()
        m.addAction(act_save)
        m.addAction(act_saveas)
        self.addAction(act_save)
        self.addAction(act_saveas)
        m.addSeparator()
        m.addAction(act_exit)

        act_settings = QAction(tr("act_settings", "Settings…"), self)
        act_settings.triggered.connect(self._show_settings)
        m_settings = self.menuBar().addMenu(tr("menu_settings", "Settings"))
        m_settings.addAction(act_settings)

        act_about = QAction(tr("act_about", "About…"), self)
        act_about.triggered.connect(self._show_about)
        m_help = self.menuBar().addMenu(tr("menu_help", "Help"))
        m_help.addAction(act_about)

        self.overview.edit_name.textEdited.connect(self._mark_dirty)
        self.overview.spin_level.valueChanged.connect(self._on_overview_level_changed)
        self.stats_tab.spins[12].valueChanged.connect(self._on_stats_level_changed)
        self.skills.table.itemChanged.connect(self._mark_dirty)

        self._refresh_ui()

    def _show_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def _show_about(self):
        dlg = AboutDialog(self)
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
        if not self.save:
            self.status.showMessage("Load a save game to begin or generate a new character")
            self.tabs.setTabEnabled(self.tabs.indexOf(self.items), False)
            return
        chk = "OK" if verify(self.save) else "INVALID"
        dirt = " *modified*" if self.dirty else ""
        self.status.showMessage(f"{self.save.path}  | checksum: {chk}{dirt}")

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
                self.overview.lbl_note.setText(tr("overview_note_empty", "Open a .d2s save file to begin."))
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
            # enable the Items tab once a save has loaded (full parse works on v105)
            self.tabs.setTabEnabled(self.tabs.indexOf(self.items), True)
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
    w.showMaximized()
    # a save path can be passed directly on the command line: python launcher.py <save.d2s>
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and os.path.isfile(args[0]):
        try:
            w.save = load_d2s(args[0])
            w.dirty = False
            w._refresh_ui()
            w.tabs.setCurrentWidget(w.items)
        except Exception:
            pass
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
