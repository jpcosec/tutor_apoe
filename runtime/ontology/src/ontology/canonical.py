"""La serialización canónica con la que se calculan identidades y huellas (09 §6.3)."""

from __future__ import annotations

import json


def canonical_json(value: object) -> bytes:
    """Claves ordenadas, separadores compactos, UTF-8 sin escapar."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
