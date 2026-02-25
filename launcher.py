#!/usr/bin/env python3
"""Launch D2R Save Editor."""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path so 'app' and 'd2s' packages can be found
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))

from app.main import main

if __name__ == "__main__":
    main()
