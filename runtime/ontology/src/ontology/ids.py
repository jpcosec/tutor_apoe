"""Ids de los objetos que crea el runtime: ULID en minúsculas, válidos como id de una `Ref` (13 §4.0).

48 bits de milisegundos más 80 aleatorios, en base32 de Crockford: ordenable por tiempo de
creación y único sin coordinación. Solo biblioteca estándar (13 I1).
"""

from __future__ import annotations

import secrets
import time

ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def new_id() -> str:
    value = (time.time_ns() // 1_000_000) << 80 | secrets.randbits(80)
    return "".join(ALPHABET[(value >> shift) & 31] for shift in range(125, -1, -5))
