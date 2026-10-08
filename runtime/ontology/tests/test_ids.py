"""13 §6.2: `new_id` da ULIDs en minúsculas, válidos como id de una `Ref` y ordenables por tiempo."""

from __future__ import annotations

import time

from ontology import Ref, new_id
from ontology.ids import ALPHABET


def test_new_id_es_un_ulid_en_minusculas_valido_como_ref() -> None:
    ids = {new_id() for _ in range(200)}

    assert len(ids) == 200
    assert all(len(i) == 26 and set(i) <= set(ALPHABET) for i in ids)
    assert str(Ref(kind="conversation", id=next(iter(ids)))).startswith("conversation:")


def test_new_id_se_ordena_por_tiempo_de_creacion() -> None:
    first = new_id()
    time.sleep(0.002)
    second = new_id()

    assert first[:10] < second[:10]
