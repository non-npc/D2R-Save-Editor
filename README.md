# Diablo II: Resurrected – Infernal Edition Save Game Editor

**D2R Save Editor** is an open-source **Diablo II: Resurrected – Infernal Edition** character save file editor for PC. 
Edit your D2R `.d2s` save files offline—change character: 
* name,
* level,
* stats,
* skills,
* quests,
* and waypoints.

  
Items are a work in progress.

> ⚠️ Use at your own risk. Always keep backups. This tool is intended for **offline** saves only.

## Screenshot

![D2R Save Editor screenshot](screenshot.jpg)

## Features

- **Open .d2s files** — Load and display Diablo II Resurrected character save files (signature, version, size, checksum, name, class, level)
- **Edit character** — Modify character name, level, stats (Strength, Dexterity, Vitality, Energy, Life, Mana, Gold, Experience), skills, quests, and waypoints
- **Save / Save As** — Updates file size and checksum automatically; creates `.bak` backups on overwrite
- **Generate new character** — Create a new D2R character save file from a blank template
- **Keyboard shortcuts** — Ctrl+S (Save), Ctrl+Shift+S (Save As)

## Install

```bash
pip install PyQt6
```

## Run

```bash
python launcher.py
```

Or:

```bash
python -m app.main
```

## Format references

- krisives/d2s-format (header, checksum): https://github.com/krisives/d2s-format
- Trevin v1.09 format notes (markers): https://user.xmission.com/~trevin/DiabloIIv1.09_File_Format.shtml

## Important limitations

- Items parsing is **incomplete** and disabled in this version.
- Quest bits beyond "completed" and the Prison of Ice special bit are preserved, but not interpreted.


## Newer save format support (v0x69) and affix editing

Recent D2R patches (and offline mod packages built on them) changed the item
encoding enough that only the first few items of the item list could be
parsed. This adds:

- Full item-list parsing for the newer format (60+ item lists parse cleanly)
- Affix value editing; affix insertion (plain stats, +X to skill, skill tab,
  charged skills, chance-to-cast); affix deletion (whole groups)
- Simple-item type change (gem tier upgrades, rune conversion)
- Equipped/inventory grids rendered from the full parse (click to select,
  quality colors, stack counts)

### Optional zh-CN display

Generate `d2s/data/i18n_zh.json` from **your own game install** (no game data
is redistributed by this repo):

    python tools/casc_extract.py "D:/Games/D2R" extracted
    python tools/build_i18n.py

Without the generated table the editor falls back to English display.

### Tests

    set D2S_TEST_SAVE=C:\path\to\your.d2s   (optional; tests skip if unset)
    python tests/test_affix_ops.py
    python tests/test_ui_smoke.py
    python tests/test_affix_i18n.py
    python tests/test_rune_convert.py
