# ontology (spec 13)

Paquete hoja: cómo se identifica, se versiona y se refiere cualquier objeto del
sistema. No sabe dónde vive ninguno; solo depende de Pydantic (13 I1).

```python
from ontology import OntologyObject, Ref, verify_refs

ref = Ref.parse("kb:ConversationStep:step-cobranza-respuesta@r1")
str(ref)                 # "kb:ConversationStep:step-cobranza-respuesta@r1" (13 I5)
ref.parts                # ("ConversationStep", "step-cobranza-respuesta")
ref.require_release()    # RefWithoutRelease si es kb sin release (13 I3)

class Trace(OntologyObject):
    schema_version: int = 1
    steps: list[Ref]

report = verify_refs(trace, {"kb": kb_resolver})   # VerifyReport(missing, unresolved_kinds, checked)
```

| Archivo | Contenido |
|---|---|
| `ref.py` | `Ref`, `RefFormatError` (con `position`), `RefWithoutRelease` |
| `provenance.py` | `Provenance` (fecha con zona, normalizada a UTC) |
| `base.py` | `OntologyObject` y `refs()` (orden de campos, sin duplicados, sin `self.ref`) |
| `verify.py` | `VerifyReport`, `verify_refs` |

13 I4 (la KB no apunta a datos) lo prueba 01 al validar la KB (V10).
