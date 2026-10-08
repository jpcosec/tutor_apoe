"""Selección de contexto con Jev (TypeSafe System One) para la KB del tutor APOS.

Dos piezas, ambas con el cliente inyectable y sin red por defecto:

- `JevSelector` cumple el `Selector` de `runtime/context` (`select(role, question, step, pool)`):
  rerank del `pool` con una pregunta `Noul` por (pregunta, átomo) en paralelo; devuelve los
  ids con noul >= `threshold`, de mayor a menor, máximo `k`. Sin API key, sin SDK o con error
  de red devuelve `None` para que el ruteador caiga a sus heurísticas.
- `JevTreeRouter` rutea por el árbol de `BranchNode` con un `Choice` por nivel y beam search
  (K=3, como el cookbook de clasificación jerárquica de TypeSafe); `route(question)` devuelve
  `[(atom_id, path_prob)]`.

SDK: `pip install typesafe-sdk` (import `typesafe_sdk`), API key en `TYPESAFE_API_KEY`,
`TypeSafeClient(model=...).system_one(state=..., questions={...}, model=...)`; cada respuesta
trae `answers[nombre].noul` (Noul) o `.choice` / `.probabilities` / `.confidence` (Choice).
`FakeJevClient` imita ese contrato de forma determinista (noul alto si hay overlap de tokens)
para tests y benchmarks sin red.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)

API_KEY_ENV = "TYPESAFE_API_KEY"
#: Mínimo de átomos que `select` devuelve si Jev respondió, aunque pocos superen el umbral.
MIN_PICK = 3
DEFAULT_MODEL = "jev-latest"
MAX_POOL = 30
BEAM_WIDTH = 3
MAX_DEPTH = 12
EPSILON = 1e-9

NOUL_NAME = "aporta_evidencia"
CHOICE_NAME = "rama"

NOUL_INSTRUCTIONS = (
    "A tutor must answer `student_question` (Spanish, about APOS theory of mathematics education, "
    "Arnon et al. 2014) using only knowledge atoms from a curated base. Does `candidate_atom` provide "
    "evidence the tutor needs for that answer: a definition, mechanism, distinction, example or claim "
    "the answer would directly rest on?"
)
NOUL_CRITERIA = {
    "true": (
        "The atom directly addresses the concept, mechanism, example or question the student asks "
        "about, or states a definition or distinction the answer must cite. Removing it would leave the "
        "answer incomplete or unsupported."
    ),
    "false": (
        "The atom belongs to the same theory but treats a different concept, stage or application, or "
        "merely shares vocabulary with the question. The answer could be written without it."
    ),
}
CHOICE_INSTRUCTIONS = (
    "`student_question` is a Spanish question about APOS theory. `current_branch` is the node of a "
    "knowledge tree we are at, and the options are its direct children (sub-branches or knowledge "
    "atoms), each described by its title and what it contains. Which child most likely holds the "
    "knowledge needed to answer the question?"
)


class JevClient(Protocol):
    """Lo que `JevSelector` y `JevTreeRouter` usan de `typesafe_sdk.TypeSafeClient`."""

    def system_one(self, state: Any, questions: Any, *, model: str | None = None) -> Any: ...


# --------------------------------------------------------------------------- cliente real


def default_client(model: str = DEFAULT_MODEL, timeout: float = 30.0) -> JevClient | None:
    """Un `TypeSafeClient` si `TYPESAFE_API_KEY` está en el entorno y el SDK importa; si no, None."""
    if not os.environ.get(API_KEY_ENV):
        log.info("sin %s en el entorno: Jev deshabilitado", API_KEY_ENV)
        return None
    try:
        from typesafe_sdk import TypeSafeClient
    except ImportError:
        log.warning("typesafe_sdk no está instalado (pip install typesafe-sdk): Jev deshabilitado")
        return None
    try:
        return TypeSafeClient(model=model, timeout=timeout)
    except Exception as exc:  # p. ej. api key inválida
        log.warning("no se pudo crear TypeSafeClient: %s", exc)
        return None


def make_noul(instructions: str, criteria: dict[str, str] | None = None) -> Any:
    """`typesafe_sdk.Noul` si el SDK está; si no, el dict de wire equivalente."""
    try:
        from typesafe_sdk import Noul

        return Noul(instructions=instructions, criteria=criteria)  # type: ignore[arg-type]
    except ImportError:
        return {"type": "noul", "instructions": instructions, "criteria": criteria}


def make_choice(instructions: str, criteria: dict[str, Any]) -> Any:
    """`typesafe_sdk.Choice` si el SDK está; si no, el dict de wire equivalente."""
    try:
        from typesafe_sdk import Choice

        return Choice(instructions=instructions, criteria=criteria)
    except ImportError:
        return {"type": "choice", "instructions": instructions, "criteria": criteria}


# --------------------------------------------------------------------------- selector


class JevSelector:
    """Rerank de un pool `(ref, resumen)` con un Noul por candidato; cumple `context.selector.Selector`."""

    def __init__(
        self,
        client: JevClient | None = None,
        model: str = DEFAULT_MODEL,
        *,
        threshold: float = 0.5,
        k: int = 8,
        max_workers: int = 8,
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.threshold = threshold
        self.k = k
        self.max_workers = max_workers
        self.timeout = timeout
        self._client = client
        self._resolved = client is not None
        #: `{ref: noul}` de la última llamada a `select`, para que la mesa muestre el puntaje real.
        self.last_scores: dict[str, float] = {}

    @property
    def client(self) -> JevClient | None:
        if not self._resolved:
            self._client = default_client(self.model, self.timeout)
            self._resolved = True
        return self._client

    def select(
        self, role: str, question: str, step: str | None, pool: list[tuple[str, str]]
    ) -> list[str] | None:
        """Las refs de `pool` con noul >= threshold, de mayor a menor, máximo `k`; None si Jev no pudo."""
        if not pool:
            return []
        scored = self.score(question, pool, role=role, step=step)
        if scored is None:
            return None
        self.last_scores = dict(scored)
        chosen = [(ref, p) for ref, p in scored if p >= self.threshold]
        # Piso: una mesa con 0–2 átomos deja al tutor sin evidencia; mejor los MIN_PICK mejores aunque
        # estén bajo el umbral (su noul queda visible en la mesa para juzgarlo).
        if len(chosen) < MIN_PICK:
            chosen = scored[:MIN_PICK]
        return [ref for ref, _ in chosen[: self.k]]

    def score(
        self, question: str, pool: list[tuple[str, str]], *, role: str = "tutor", step: str | None = None
    ) -> list[tuple[str, float]] | None:
        """`(ref, noul)` para cada candidato del pool (≤ MAX_POOL), ordenados de mayor a menor; None si falló."""
        client = self.client
        if client is None:
            return None
        pool = pool[:MAX_POOL]

        def one(item: tuple[str, str]) -> float:
            ref, summary = item
            state = {
                "student_question": question,
                "conversation_step": step or "",
                "agent_role": role,
                "candidate_atom": {"id": ref, "summary": summary},
            }
            response = client.system_one(
                state=state,
                questions={NOUL_NAME: make_noul(NOUL_INSTRUCTIONS, NOUL_CRITERIA)},
                model=self.model,
            )
            return float(response.answers[NOUL_NAME].noul)

        try:
            with ThreadPoolExecutor(max_workers=max(1, min(self.max_workers, len(pool)))) as executor:
                probs = list(executor.map(one, pool))
        except Exception as exc:  # red, auth, cuota: el ruteador sigue con heurísticas
            log.warning("JevSelector falló (%s): %s", type(exc).__name__, exc)
            return None
        ranked = sorted(zip((ref for ref, _ in pool), probs), key=lambda item: -item[1])
        log.debug("JevSelector: %s", ranked[:5])
        return ranked


# --------------------------------------------------------------------------- ruteo jerárquico


@dataclass(frozen=True)
class _Node:
    id: str
    title: str
    summary: str
    is_branch: bool


@dataclass
class _Path:
    node: _Node
    product: float = 1.0
    decisions: int = 0
    trail: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.product ** (1 / self.decisions) if self.decisions else 1.0


class JevTreeRouter:
    """Beam search (K=`beam_width`) por el árbol de BranchNode con un Choice por nivel.

    `route(question)` devuelve hojas `(atom_id, path_prob)`; `path_prob` es la media geométrica de
    las probabilidades de las aristas elegidas (como el cookbook), de mayor a menor. None si Jev no
    pudo (sin API key, sin SDK o error de red).
    """

    def __init__(
        self,
        kb: Any,
        client: JevClient | None = None,
        model: str = DEFAULT_MODEL,
        *,
        root: str = "branch-apos",
        beam_width: int = BEAM_WIDTH,
        max_depth: int = MAX_DEPTH,
        max_workers: int = 8,
        timeout: float = 30.0,
    ) -> None:
        from tutor import world

        self._world = world
        self.kb = kb
        self.model = model
        self.root = root
        self.beam_width = beam_width
        self.max_depth = max_depth
        self.max_workers = max_workers
        self.timeout = timeout
        self._client = client
        self._resolved = client is not None
        self._children: dict[str, list[_Node]] = {}

    @property
    def client(self) -> JevClient | None:
        if not self._resolved:
            self._client = default_client(self.model, self.timeout)
            self._resolved = True
        return self._client

    # árbol ------------------------------------------------------------------

    def _node(self, doc: dict[str, Any]) -> _Node:
        return _Node(doc["id"], doc.get("title") or doc["id"], doc.get("summary") or "", doc.get("model") == "BranchNode")

    def children(self, node_id: str) -> list[_Node]:
        if node_id not in self._children:
            kids = [self._node(d) for d in self._world.children(self.kb, node_id)]
            self._children[node_id] = sorted(kids, key=lambda n: (not n.is_branch, n.id))
        return self._children[node_id]

    def _describe(self, node: _Node) -> dict[str, Any]:
        """Lo que el modelo ve de una opción: título y, para ramas, los títulos de lo que contienen."""
        if not node.is_branch:
            return {"kind": "knowledge atom", "title": node.title, "summary": node.summary[:280]}
        contents = [kid.title for kid in self.children(node.id)]
        return {"kind": "branch", "title": node.title, "contains": contents[:12]}

    # búsqueda ---------------------------------------------------------------

    def route(self, question: str) -> list[tuple[str, float]] | None:
        client = self.client
        if client is None:
            return None
        root_doc = self._world.get_atom(self.kb, self.root)
        if root_doc is None:
            raise KeyError(self.root)
        beam = [_Path(self._node(root_doc))]
        try:
            for _ in range(self.max_depth):
                open_paths = [p for p in beam if p.node.is_branch]
                if not open_paths:
                    break
                finished = [p for p in beam if not p.node.is_branch]
                with ThreadPoolExecutor(max_workers=max(1, min(self.max_workers, len(open_paths)))) as executor:
                    expansions = list(executor.map(lambda p: self._expand(client, question, p), open_paths))
                expanded = [child for group in expansions for child in group]
                beam = sorted(finished + expanded, key=lambda p: -p.score)[: self.beam_width]
        except Exception as exc:
            log.warning("JevTreeRouter falló (%s): %s", type(exc).__name__, exc)
            return None
        leaves = [(p.node.id, round(p.score, 6)) for p in beam if not p.node.is_branch]
        log.debug("JevTreeRouter: %s", leaves)
        return leaves

    def _expand(self, client: JevClient, question: str, path: _Path) -> list[_Path]:
        kids = self.children(path.node.id)
        if not kids:
            return []
        if len(kids) == 1:  # sin decisión: probabilidad 1 sin llamar al modelo
            return [_Path(kids[0], path.product, path.decisions, path.trail + [path.node.title])]
        probabilities = self.choose(client, question, path, kids)
        out = []
        for kid in kids:
            p = max(probabilities.get(kid.id, 0.0), EPSILON)
            out.append(_Path(kid, path.product * p, path.decisions + 1, path.trail + [path.node.title]))
        return out

    def choose(self, client: JevClient, question: str, path: _Path, kids: list[_Node]) -> dict[str, float]:
        """Un Choice sobre los hijos de `path.node`; devuelve {child_id: probabilidad}."""
        keys = {f"c{i}": kid for i, kid in enumerate(kids)}
        criteria = {key: self._describe(kid) for key, kid in keys.items()}
        state = {
            "student_question": question,
            "current_branch": {"title": path.node.title, "path": path.trail + [path.node.title]},
        }
        response = client.system_one(
            state=state,
            questions={CHOICE_NAME: make_choice(CHOICE_INSTRUCTIONS, criteria)},
            model=self.model,
        )
        probs = dict(response.answers[CHOICE_NAME].probabilities)
        return {kid.id: float(probs.get(key, 0.0)) for key, kid in keys.items()}


# --------------------------------------------------------------------------- fake determinista

_STOP = {
    "que", "qué", "cual", "cuál", "como", "cómo", "por", "para", "con", "sin", "del", "las", "los", "una",
    "uno", "unos", "unas", "the", "and", "apos", "teoria", "teoría", "entre", "sobre", "hacia", "desde",
    "puede", "pueden", "cuando", "donde", "esta", "este", "esto", "estudiante", "estudiantes", "dice",
    "dicen", "significa", "quiere", "decir", "explica", "explicar", "ejemplo", "libro", "mediante", "mas",
    "más", "muy", "son", "ser", "hay", "tiene", "tienen", "sus", "ella", "ellos", "nos", "respecto",
}


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()


def fake_tokens(text: str) -> set[str]:
    """Raíces crudas (7 letras) de las palabras con ≥ 4 letras, sin acentos ni stopwords."""
    return {w[:7] for w in re.findall(r"[a-z0-9]+", _norm(text)) if len(w) >= 4 and w not in _STOP}


def _flatten(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten(v) for v in value)
    return "" if value is None else str(value)


def _as_dict(question: Any) -> dict[str, Any]:
    if isinstance(question, dict):
        return question
    if hasattr(question, "model_dump"):
        return question.model_dump()
    return {"type": getattr(question, "type", None), "criteria": getattr(question, "criteria", None)}


@dataclass(frozen=True)
class FakeNoulAnswer:
    noul: float
    type: str = "noul"


@dataclass(frozen=True)
class FakeChoiceAnswer:
    choice: str
    probabilities: dict[str, float]
    confidence: float
    type: str = "choice"


@dataclass(frozen=True)
class FakeResponse:
    answers: dict[str, Any]
    model: str = "fake-jev"


class FakeJevClient:
    """Cliente determinista sin red con el contrato de `system_one`.

    Noul: alto si los tokens de `state["student_question"]` aparecen en el resto del estado
    (0.1 sin overlap; 0.55 + 0.1·n acotado a 0.97). Choice: probabilidades proporcionales al
    overlap de cada opción (+ suavizado), `choice` = argmax. Guarda `calls` para los tests.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def system_one(self, state: Any, questions: Any, *, model: str | None = None) -> FakeResponse:
        self.calls.append({"state": state, "questions": questions, "model": model})
        query = state.get("student_question", "") if isinstance(state, dict) else str(state)
        rest = {k: v for k, v in state.items() if k != "student_question"} if isinstance(state, dict) else {}
        q_tokens = fake_tokens(query)
        answers: dict[str, Any] = {}
        for name, question in questions.items():
            spec = _as_dict(question)
            if spec.get("type") == "noul":
                n = len(q_tokens & fake_tokens(_flatten(rest)))
                answers[name] = FakeNoulAnswer(0.1 if n == 0 else min(0.97, 0.55 + 0.1 * n))
            elif spec.get("type") == "choice":
                criteria = spec.get("criteria") or {}
                raw = {key: len(q_tokens & fake_tokens(f"{key} {_flatten(desc)}")) + 0.1 for key, desc in criteria.items()}
                total = sum(raw.values()) or 1.0
                probs = {key: v / total for key, v in raw.items()}
                best = max(probs, key=probs.get)  # type: ignore[arg-type]
                even = 1 / max(len(probs), 1)
                confidence = max(0.0, (probs[best] - even) / (1 - even)) if len(probs) > 1 else 1.0
                answers[name] = FakeChoiceAnswer(best, probs, confidence)
            else:
                raise ValueError(f"FakeJevClient no soporta {spec.get('type')!r}")
        return FakeResponse(answers)


__all__ = [
    "API_KEY_ENV",
    "BEAM_WIDTH",
    "CHOICE_INSTRUCTIONS",
    "DEFAULT_MODEL",
    "FakeJevClient",
    "JevClient",
    "JevSelector",
    "JevTreeRouter",
    "MAX_POOL",
    "NOUL_CRITERIA",
    "NOUL_INSTRUCTIONS",
    "default_client",
    "fake_tokens",
    "make_choice",
    "make_noul",
]
