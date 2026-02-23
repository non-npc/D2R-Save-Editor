"""
Settings dialog for D2R Save Editor.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QHBoxLayout, QLabel, QDialogButtonBox, QFileDialog
)

from .settings import get_game_folder, set_game_folder


class SettingsDialog(QDialog):
    """Dialog to configure application settings including game folder path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)

        layout = QVBoxLayout()
        self.setLayout(layout)

        form = QFormLayout()
        row = QHBoxLayout()
        self.edit_game_folder = QLineEdit()
        self.edit_game_folder.setPlaceholderText("e.g. C:\\Program Files (x86)\\Diablo II Resurrected")
        self.edit_game_folder.setText(get_game_folder())
        row.addWidget(self.edit_game_folder)

        btn_browse = QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse_game_folder)
        row.addWidget(btn_browse)

        form.addRow("Game folder:", row)
        layout.addLayout(form)

        hint = QLabel(
            "Path to the D2/D2R installation folder. Used to find item data in MPQ files "
            "(e.g. ItemStatCost.txt, Armor.txt, Weapons.txt, Misc.txt)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_game_folder(self):
        start = self.edit_game_folder.text().strip() or str(Path.home())
        folder = self._get_existing_directory("Select D2/D2R Game Folder", start)
        if folder:
            self.edit_game_folder.setText(folder)

    def _get_existing_directory(self, caption: str, start: str) -> str:
        return QFileDialog.getExistingDirectory(self, caption, start)

    def _accept(self):
        path = self.edit_game_folder.text().strip()
        set_game_folder(path)
        self.accept()
