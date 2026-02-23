"""
Persistent application settings. Uses QSettings for cross-platform storage.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSettings

_SETTINGS_ORG = "D2REditor"
_SETTINGS_APP = "D2R Save Editor"
_KEY_GAME_FOLDER = "game_folder"


def get_game_folder() -> str:
    """Return the configured D2/D2R game folder path, or empty string if not set."""
    s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    return s.value(_KEY_GAME_FOLDER, "", type=str)


def set_game_folder(path: str) -> None:
    """Store the D2/D2R game folder path."""
    s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    s.setValue(_KEY_GAME_FOLDER, path)


def get_game_folder_path() -> Optional[Path]:
    """Return the game folder as a Path, or None if not set or invalid."""
    p = get_game_folder().strip()
    if not p:
        return None
    path = Path(p)
    return path if path.exists() else None
