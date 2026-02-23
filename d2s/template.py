"""
Template save file for "Generate new Character" feature.
Loads blank character from embedded TEMPLATE_BYTES in template_data.
"""
from __future__ import annotations

from typing import Optional


def get_template_bytes() -> Optional[bytes]:
    """
    Return template save file bytes.
    Returns None if no template is available.
    """
    try:
        from . import template_data
        if hasattr(template_data, "TEMPLATE_BYTES") and template_data.TEMPLATE_BYTES:
            return template_data.TEMPLATE_BYTES
    except ImportError:
        pass

    return None
