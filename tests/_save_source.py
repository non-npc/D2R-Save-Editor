"""Shared helper for editor test scripts.

Resolves the test save location (never a live save):
1. D2S_TEST_SAVE environment variable (absolute path to a .d2s file)
2. Repo-relative sync/Amenda.d2s (local dev convenience)

Call ensure_test_save() after imports; it exits with a friendly message
when no test save is available so upstream contributors aren't blocked.
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_save_path() -> str:
    env = os.environ.get("D2S_TEST_SAVE")
    if env and os.path.isfile(env):
        return env
    local = REPO_ROOT / "sync" / "Amenda.d2s"
    if local.is_file():
        return str(local)
    return ""


def ensure_test_save() -> str:
    path = test_save_path()
    if not path:
        print(
            "[skip] no test save found. Set D2S_TEST_SAVE to a .d2s file "
            "(e.g. your own offline save) and re-run."
        )
        sys.exit(0)
    return path


def repo_sys_path() -> None:
    sys.path.insert(0, str(REPO_ROOT))
