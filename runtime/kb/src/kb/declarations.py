"""`SldbDeclarations`: fachada declarativa sobre una KB sldb (api-canonica §06).

Envuelve `KnowledgeBase` y expone los accesos declarativos del contrato canónico:
`resolve(ref)` (documento), `machine(ref)` (definición compilada desde el grafo REAL de sldb),
`project(selector)` (conocimiento con semántica KnowledgeSelector AND/OR, subtipos y lifecycle)
y `fingerprint()` (raíz Merkle de la KB). No reimplementa el almacenamiento de sldb.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cognitive import (
    KnowledgeSelector,
    MachineDefinition,
    machine_definition_hash,
)
from kb.facade import KnowledgeBase
from kb.loading.sldb_gateway import Embedder
from kb.machines import GraphCompileError, GraphCompiler, collect_machine_graph
from kb.model.catalog import ModelInfo
from kb.model.document import Document
from ontology import Ref

log = logging.getLogger(__name__)


class SldbDeclarations:
    """Fachada declarativa canónica; portador neutral e inyectable.

    `machine` usa el compilador de grafo real de sldb; `project` aplica el selector exacto.
    `store` explicita la ruta al store `.sldb` (necesaria para leer el grafo real); si no se
    pasa, se deriva de la KB cargada.
    """

    def __init__(
        self,
        kb: KnowledgeBase,
        *,
        compiler: GraphCompiler | None = None,
        store: Path | None = None,
        bound_release_id: str | None = None,
        verified_fingerprint: str | None = None,
    ) -> None:
        self._kb = kb
        self._compiler = compiler or GraphCompiler()
        self._store = store or self._derive_store()
        if (bound_release_id is None) != (verified_fingerprint is None):
            raise ValueError("release binding requires release ID and verified source fingerprint")
        if verified_fingerprint is not None and verified_fingerprint != kb.fingerprint:
            raise ValueError("verified release fingerprint differs from source KB")
        self._bound_release_id = bound_release_id
        self._verified_fingerprint = verified_fingerprint

    @classmethod
    def open(cls, root: Path, *, embedder: Embedder | None = None) -> SldbDeclarations:
        """Abre una KB y la envuelve en la fachada declarativa."""
        kb = KnowledgeBase.open(root, embedder=embedder)
        loaded = kb._kb  # pyright: ignore[reportPrivateUsage]
        return cls(kb, store=loaded.store)

    def _derive_store(self) -> Path:
        loaded = self._kb._kb  # pyright: ignore[reportPrivateUsage]
        return loaded.store

    # -- contrato -------------------------------------------------------------

    def resolve(self, ref: Ref | str) -> Document:
        """Documento por `Modelo:nombre` (o `nombre`); desaparece si no existe o ambiguo."""
        parsed = Ref.parse(ref) if isinstance(ref, str) and ref.startswith("kb:") else ref
        if isinstance(parsed, str) and "@" in parsed:
            parsed = Ref.parse(f"kb:{parsed}")
        if isinstance(parsed, Ref) and parsed.kind != "kb":
            raise ValueError(f"declaration reference must belong to kb: {parsed}")
        if isinstance(parsed, Ref) and parsed.release_id is not None:
            self._require_release(parsed.release_id)
        elif self._bound_release_id is not None:
            self._require_release(self._bound_release_id)
        return self._kb.get(parsed.id if isinstance(parsed, Ref) else parsed)

    def _require_release(self, release_id: str) -> None:
        if release_id != self._bound_release_id or self._verified_fingerprint is None:
            raise GraphCompileError(f"release {release_id} has no verified source binding")
        from kb.loading.sldb_gateway import store_fingerprint

        current = store_fingerprint(self._store).kb_fingerprint
        if current != self._verified_fingerprint:
            raise GraphCompileError(f"verified release source changed: {release_id}")

    def machine(self, ref: Ref | str) -> MachineDefinition:
        """Compila la `MachineDefinition` de una máquina leyendo el grafo TIPADO real de sldb.

        Si `ref` lleva pin de release (`Ref.release_id`), ese pin se conserva en el ref
        compilado y el content_hash se recalcula sobre el ref pineado (y es el mismo que
        usaría el motor/core de ese pin). Una fuente bound hereda su release; la fuente
        actual/unbound compila refs locales sin release y rechaza pins no verificados.
        """
        parsed = Ref.parse(ref) if isinstance(ref, str) and ref.startswith("kb:") else ref
        if isinstance(parsed, str) and "@" in parsed:
            parsed = Ref.parse(f"kb:{parsed}")
        incoming_release = (parsed.release_id if isinstance(parsed, Ref) else None) or self._bound_release_id
        try:
            target = self.resolve(parsed).key
        except KeyError as err:
            raise GraphCompileError(f"missing machine {parsed}") from err
        loaded = self._kb._kb  # pyright: ignore[reportPrivateUsage]
        graph = collect_machine_graph(
            self._kb.documents(),
            self._store,
            pythonpath=str(loaded.pythonpath),
            machine_ref=target,
        )
        definition = self._compiler.compile(graph)
        if incoming_release is not None:
            self._require_release(incoming_release)
            pinned_ref = Ref(kind="kb", id=definition.ref.id, release_id=incoming_release)
            pinned = definition.model_copy(update={"ref": pinned_ref, "content_hash": ""})
            return pinned.model_copy(update={"content_hash": machine_definition_hash(pinned)})
        return definition

    def project(self, selector: KnowledgeSelector | None = None) -> tuple[Document, ...]:
        """Conocimiento elegible del alcance explícito; semántica KnowledgeSelector AND/OR.

        - sin selector → documentos elegibles del alcance del consumidor;
        - `model_names` (incluye subtipos registrados por ancestría), `tags_all` → AND;
        - `tags_any` → OR; `relation_from` / `projection_name` filtran;
        - `eligible`/lifecycle filtra antes de seleccionar; orden por `document.key`.
        """
        if self._bound_release_id is not None:
            self._require_release(self._bound_release_id)
        documents = self._kb.documents()
        documents = self._scope(documents, selector)
        documents = self._applicable(documents, selector)
        return tuple(sorted(documents, key=lambda d: d.key))

    def fingerprint(self) -> str:
        """La raíz del árbol de Merkle de sldb (misma huella, misma KB)."""
        return self._kb.fingerprint

    def documents(self) -> list[Document]:
        return self._kb.documents()

    # -- helpers --------------------------------------------------------------

    def _scope(self, documents: list[Document], selector: KnowledgeSelector | None) -> list[Document]:
        if selector is None:
            return [d for d in documents if self._eligible(d)]
        scope = list(documents)
        if selector.relation_from is not None:
            scope = self._relation_window(scope, selector.relation_from)
        if selector.projection_name is not None:
            projection_keys = {d.key for d in self._kb.in_projection(selector.projection_name)}
            scope = [d for d in scope if d.key in projection_keys or d.model in self._structural()]
        # eligible/lifecycle: los documentos bajo tags de bloqueo no entran.
        return [d for d in scope if self._eligible(d)]

    @staticmethod
    def _eligible(document: Document) -> bool:
        status = document.payload.get("status")
        return document.eligible and status not in (
            "proposed",
            "validated",
            "superseded",
            "retired",
            "deprecated",
            "inactive",
        )

    def _relation_window(self, documents: list[Document], relation_from: Ref) -> list[Document]:
        key = self.resolve(relation_from).key
        targets: set[str] = set()
        for relation in self._kb.outgoing(key):
            targets.add(relation.target_ref)
        return [d for d in documents if d.key in targets]

    def _applicable(self, documents: list[Document], selector: KnowledgeSelector | None) -> list[Document]:
        if selector is None:
            return documents
        matched: list[Document] = []
        for doc in documents:
            if not self._matches(doc, selector):
                continue
            matched.append(doc)
        return matched

    def _matches(self, doc: Document, selector: KnowledgeSelector) -> bool:
        if selector.model_names and not self._ancestor_match(doc.model, selector.model_names):
            return False
        # tags_all → AND
        if selector.tags_all and not all(t in doc.all_tags for t in selector.tags_all):
            return False
        # tags_any → OR
        return not (selector.tags_any and not any(t in doc.all_tags for t in selector.tags_any))

    def _ancestor_match(self, model: str, model_names: tuple[str, ...]) -> bool:
        info = self._model_info(model)
        if info is None:
            raise ValueError(f"unregistered model {model}")
        loaded = self._kb._kb  # pyright: ignore[reportPrivateUsage]
        model_type = loaded.model_types.get(model)
        if model_type is None:
            raise ValueError(f"missing imported model {model}")
        ancestors = {cls.__name__ for cls in model_type.__mro__}
        if not set(info.base_models) <= ancestors:
            raise ValueError(f"registry ancestry disagrees with imported model {model}")
        return any(
            name in ancestors and (name == model or self._model_info(name) is not None)
            for name in model_names
        )

    def _model_info(self, name: str) -> ModelInfo | None:
        return next((m for m in self._kb.models if m.name == name), None)

    def _structural(self) -> frozenset[str]:
        return frozenset({"RelationDoc", "RelationTypeDoc"})


__all__ = ["SldbDeclarations"]
