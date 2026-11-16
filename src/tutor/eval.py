"""Evaluación del tutor (su razonamiento) y de la KB (sus átomos).

    tutor eval run   [--kb] [--questions benchmarks/apos_questions.yaml] [--model] [--selector auto|heuristic|jev]
                     [--k 8] [--limit N] [--out runs/evals/<ts>-<model>-<selector>/]
    tutor eval report  <dir>            # reimprime el resumen de una corrida
    tutor eval compare <dirA> <dirB>    # dos corridas lado a lado (heuristic vs jev, dos modelos…)
    tutor eval turn "<pregunta>" [--kb] [--model]   # UN turno explicado: mesa, citas, groundedness
    tutor eval atoms [--kb] [--evals runs/evals/] [--json out.json]   # salud de la KB

Por pregunta (`run`) se mide:

- **Retrieval**: hit@1, hit@k, MRR y tag-hit@k sobre `expected_atom_ids` (fórmulas de
  `benchmarks.run.evaluate`), y el noul máximo/mínimo de la mesa si el selector fue Jev (un
  máximo bajo = «la KB no cubre esto»).
- **Citas**: ids `[atom-…]` en la respuesta → `valid` (existe en la KB), `in_mesa` (estaba en la
  mesa o fue leído con `show_atom`; citar fuera de eso = alucinación de id), `coverage`
  (expected citados / expected).
- **Groundedness (Jev)**: la respuesta se parte en oraciones; por cada oración con cita, un Noul
  «¿el átomo citado respalda esta afirmación?» (estado: claim + título/respuesta del átomo). Se
  reporta la fracción respaldada y las oraciones no respaldadas. Sin `TYPESAFE_API_KEY` → `skipped`.
- **Respuesta**: longitud, nº de citas, latencia, tokens, costo si se conoce.

Se engancha sin tocar `cli`/`mcp_server`: `register_cli(app)` suma el sub-typer `eval`;
`register_mcp(server, state, safe, annotations)` suma `eval_run`, `explain_turn`, `eval_atoms`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
import sys
import time
import unicodedata
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field

from tutor import world

log = logging.getLogger(__name__)

DEFAULT_QUESTIONS = Path("benchmarks") / "apos_questions.yaml"
DEFAULT_EVALS_DIR = Path("runs") / "evals"
RESULTS_FILE = "results.json"
REPORT_FILE = "report.md"
#: Umbral de noul para considerar una oración respaldada por el átomo citado.
GROUNDED_THRESHOLD = 0.5
#: Respuestas de átomo (chars) por debajo/encima de esto se marcan en `eval atoms`.
SHORT_ANSWER_CHARS = 80
LONG_ANSWER_CHARS = 1200
#: Títulos casi duplicados: Jaccard de palabras del título normalizado o coseno del embedding hash.
DUP_TITLE_RATIO = 0.9
DUP_EMBED_SIM = 0.9
SELECTOR_MODES = ("auto", "heuristic", "jev")

CITATION_RE = re.compile(r"\[(?:KnowledgeAtom:)?(atom-[a-z0-9][a-z0-9-]*)\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")

GROUNDED_NAME = "respaldada"
GROUNDED_INSTRUCTIONS = (
    "`claim` is one sentence from a tutor's answer (Spanish) to a student about APOS theory of "
    "mathematics education. `cited_atom` is the knowledge atom (title and curated answer) the tutor "
    "cited as the evidence for that sentence. Does the atom state the claim, or directly imply that "
    "it is true?"
)
GROUNDED_CRITERIA = {
    "true": (
        "The atom states the claim or what it says directly implies it; paraphrase, summary or a "
        "weaker restatement of the atom counts as supported."
    ),
    "false": (
        "The atom does not address what the claim asserts, or says the opposite; the claim adds "
        "facts, examples, numbers, names or conclusions the atom does not contain."
    ),
}


# --------------------------------------------------------------------------------------------
# Preguntas
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    question: str
    expected_atom_ids: tuple[str, ...] = ()
    expected_tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "question": self.question, "expected_atom_ids": list(self.expected_atom_ids), "expected_tags": list(self.expected_tags)}


def questions_from(items: Iterable[Any]) -> list[EvalQuestion]:
    """`EvalQuestion`s desde dicts, modelos pydantic o `benchmarks.run.Question`."""
    out: list[EvalQuestion] = []
    for i, item in enumerate(items):
        data = item if isinstance(item, dict) else (item.model_dump() if hasattr(item, "model_dump") else asdict(item))
        out.append(
            EvalQuestion(
                str(data.get("id") or f"q{i + 1:02d}"),
                str(data["question"]),
                tuple(str(a) for a in data.get("expected_atom_ids") or ()),
                tuple(str(t) for t in data.get("expected_tags") or ()),
            )
        )
    return out


def load_questions(path: Path | str | None = None) -> list[EvalQuestion]:
    """El YAML del benchmark (`questions: [{id, question, expected_atom_ids, expected_tags?}]`)."""
    import yaml

    path = Path(path) if path else questions_path_default()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return questions_from(data.get("questions") or [])


def questions_path_default() -> Path:
    return world.repo_root() / DEFAULT_QUESTIONS


def evals_dir_default() -> Path:
    return world.repo_root() / DEFAULT_EVALS_DIR


# --------------------------------------------------------------------------------------------
# Citas y oraciones
# --------------------------------------------------------------------------------------------


def extract_citations(text: str) -> list[str]:
    """Los ids `[atom-…]` (o `[KnowledgeAtom:atom-…]`) citados, sin repetir y en orden."""
    seen: list[str] = []
    for atom_id in CITATION_RE.findall(text or ""):
        if atom_id not in seen:
            seen.append(atom_id)
    return seen


def split_sentences(text: str) -> list[str]:
    """Oraciones de la respuesta (por `.?!` y saltos de línea, sin viñetas); un fragmento que sea
    solo citas (`… proceso. [atom-x]`) se pega a la oración anterior."""
    sentences: list[str] = []
    for raw in _SENTENCE_SPLIT.split(text or ""):
        piece = _BULLET.sub("", raw).strip()
        if not piece:
            continue
        if sentences and not CITATION_RE.sub("", piece).strip(" .,;:"):
            sentences[-1] = f"{sentences[-1]} {piece}"
        else:
            sentences.append(piece)
    return sentences


def cited_sentences(text: str) -> list[dict[str, Any]]:
    """`[{sentence, atom_ids}]` para las oraciones que citan al menos un átomo."""
    out = []
    for sentence in split_sentences(text):
        ids = extract_citations(sentence)
        if ids:
            out.append({"sentence": sentence, "atom_ids": ids})
    return out


def citation_metrics(
    reply: str, *, mesa_ids: Iterable[str], known_ids: Iterable[str], expected_ids: Iterable[str], reads: Iterable[str] = ()
) -> dict[str, Any]:
    """`cited`, `valid`, `invalid`, `in_mesa`, `out_of_mesa` (ids válidos citados sin estar en la mesa
    ni leídos con `show_atom`), `coverage` (expected citados / expected; None sin expected)."""
    cited = extract_citations(reply)
    mesa, known, expected, read = set(mesa_ids), set(known_ids), list(dict.fromkeys(expected_ids)), set(reads)
    valid = [c for c in cited if c in known]
    invalid = [c for c in cited if c not in known]
    in_mesa = [c for c in valid if c in mesa or c in read]
    out_of_mesa = [c for c in valid if c not in mesa and c not in read]
    expected_cited = [e for e in expected if e in cited]
    return {
        "cited": cited,
        "n_cited": len(cited),
        "valid": valid,
        "invalid": invalid,
        "in_mesa": in_mesa,
        "out_of_mesa": out_of_mesa,
        "valid_rate": (len(valid) / len(cited)) if cited else None,
        "in_mesa_rate": (len(in_mesa) / len(valid)) if valid else None,
        "expected_cited": expected_cited,
        "coverage": (len(expected_cited) / len(expected)) if expected else None,
    }


# --------------------------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------------------------


def _benchmarks():
    """`benchmarks.run` (sumando la raíz del repo al path si hace falta); None si no está."""
    try:
        from benchmarks import run as bench  # type: ignore[import-not-found]

        return bench
    except ImportError:
        root = str(world.repo_root())
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            from benchmarks import run as bench  # type: ignore[import-not-found]

            return bench
        except ImportError:
            return None


def retrieval_metrics(mesa_ids: list[str], question: EvalQuestion, k: int, atom_tags: dict[str, list[str]]) -> dict[str, Any]:
    """hit@1, hit@k, rr, tag-hit@k y `first_hit_rank` de la mesa frente a `expected_atom_ids`
    (misma fórmula que `benchmarks.run.evaluate`). Sin expected → métricas None (`scored: False`)."""
    ids = list(mesa_ids)[:k]
    if not question.expected_atom_ids:
        return {"scored": False, "first_hit_rank": None, "hit@1": None, "hit@k": None, "rr": None, "tag_hit@k": None, "expected_in_mesa": []}
    bench = _benchmarks()
    if bench is not None:
        bq = bench.Question(question.id, question.question, question.expected_atom_ids, question.expected_tags)
        rows, _ = bench.evaluate(lambda _q, _k: ids, [bq], k, atom_tags)
        row = rows[0]
        hit_k, tag_hit = row["hit@k"], row["tag_hit@k"]
        rank, rr, hit_1 = row["first_hit_rank"], row["rr"], row["hit@1"]
    else:  # misma fórmula, local
        expected = set(question.expected_atom_ids)
        rank = next((i + 1 for i, a in enumerate(ids) if a in expected), None)
        hit_1, hit_k, rr = int(rank == 1), int(rank is not None), (1 / rank if rank else 0.0)
        tag_hit = int(any(set(atom_tags.get(a, [])) & set(question.expected_tags) for a in ids))
    return {
        "scored": True,
        "first_hit_rank": rank,
        "hit@1": hit_1,
        "hit@k": hit_k,
        "rr": rr,
        "tag_hit@k": tag_hit,
        "expected_in_mesa": [e for e in question.expected_atom_ids if e in ids],
    }


def mesa_nouls(mesa: dict[str, Any]) -> dict[str, Any]:
    """Si el selector fue Jev, los puntajes de los átomos elegidos por él son nouls: máximo y mínimo."""
    log_ = {e["type"]: e["detail"] for e in mesa.get("reasoning_log", []) if isinstance(e, dict)}
    selector = log_.get("selector", "heuristic")
    scores = [float(i["score"]) for i in mesa.get("items", []) if i.get("role") == "llm"]
    if selector != "llm" or not scores:
        return {"selector": "jev" if selector == "llm" else "heuristic", "max_noul": None, "min_noul": None}
    return {"selector": "jev", "max_noul": round(max(scores), 4), "min_noul": round(min(scores), 4)}


# --------------------------------------------------------------------------------------------
# Groundedness con Jev
# --------------------------------------------------------------------------------------------


class Grounder:
    """Un Noul por (oración, átomo citado): ¿el átomo respalda la oración? Cliente inyectable
    (`FakeJevClient` en tests); sin `TYPESAFE_API_KEY` ni SDK, `check` devuelve `status: skipped`."""

    def __init__(self, client: Any | None = None, *, model: str | None = None, threshold: float = GROUNDED_THRESHOLD, max_workers: int = 8) -> None:
        from tutor.selector_jev import DEFAULT_MODEL

        self.model = model or DEFAULT_MODEL
        self.threshold = threshold
        self.max_workers = max_workers
        self._client = client
        self._resolved = client is not None

    @property
    def client(self) -> Any | None:
        if not self._resolved:
            from tutor.selector_jev import default_client

            self._client = default_client(self.model)
            self._resolved = True
        return self._client

    def check(self, reply: str, kb: Any) -> dict[str, Any]:
        """`{status, threshold, n_claims, n_supported, fraction_supported, claims[{sentence, atom_ids, noul, supported, supported_by}], unsupported[]}`."""
        from tutor.selector_jev import API_KEY_ENV, make_noul

        claims = cited_sentences(reply)
        base = {"threshold": self.threshold, "n_claims": len(claims), "claims": [], "unsupported": []}
        client = self.client
        if client is None:
            return {**base, "status": "skipped", "reason": f"sin {API_KEY_ENV} o sin typesafe_sdk", "n_supported": None, "fraction_supported": None}
        if not claims:
            return {**base, "status": "ok", "n_supported": 0, "fraction_supported": None}

        pairs = [(ci, atom_id) for ci, claim in enumerate(claims) for atom_id in claim["atom_ids"]]

        def one(pair: tuple[int, str]) -> float | None:
            ci, atom_id = pair
            atom = world.get_atom(kb, atom_id)
            if atom is None:
                return None  # id inválido: no hay átomo contra el que verificar
            state = {
                "claim": CITATION_RE.sub("", claims[ci]["sentence"]).strip(),
                "cited_atom": {"id": atom_id, "title": atom.get("title"), "answer": str(atom.get("summary") or "")[:1500]},
            }
            response = client.system_one(state=state, questions={GROUNDED_NAME: make_noul(GROUNDED_INSTRUCTIONS, GROUNDED_CRITERIA)}, model=self.model)
            return float(response.answers[GROUNDED_NAME].noul)

        try:
            with ThreadPoolExecutor(max_workers=max(1, min(self.max_workers, len(pairs)))) as pool:
                nouls = list(pool.map(one, pairs))
        except Exception as exc:  # red, auth, cuota: la métrica queda como skipped, no tumba la corrida
            log.warning("groundedness falló (%s): %s", type(exc).__name__, exc)
            return {**base, "status": "skipped", "reason": f"{type(exc).__name__}: {exc}", "n_supported": None, "fraction_supported": None}

        by_claim: dict[int, dict[str, float]] = {}
        for (ci, atom_id), noul in zip(pairs, nouls):
            if noul is not None:
                by_claim.setdefault(ci, {})[atom_id] = round(noul, 4)
        rows, unsupported = [], []
        for ci, claim in enumerate(claims):
            scores = by_claim.get(ci, {})
            best = max(scores, key=scores.get) if scores else None  # type: ignore[arg-type]
            noul = scores[best] if best else 0.0
            supported = bool(best) and noul >= self.threshold
            rows.append({**claim, "nouls": scores, "noul": noul, "supported": supported, "supported_by": best if supported else None})
            if not supported:
                unsupported.append({"sentence": claim["sentence"], "atom_ids": claim["atom_ids"], "noul": noul})
        n_sup = sum(1 for r in rows if r["supported"])
        return {**base, "status": "ok", "claims": rows, "unsupported": unsupported, "n_supported": n_sup, "fraction_supported": n_sup / len(rows)}


# --------------------------------------------------------------------------------------------
# Selector y modelo
# --------------------------------------------------------------------------------------------


@contextlib.contextmanager
def _selector_env(mode: str) -> Iterator[None]:
    """`answer()` toma el selector de `TUTOR_SELECTOR` cuando recibe None: lo fijamos a lo pedido."""
    from tutor.agent import SELECTOR_ENV

    before = os.environ.get(SELECTOR_ENV)
    os.environ[SELECTOR_ENV] = mode
    try:
        yield
    finally:
        if before is None:
            os.environ.pop(SELECTOR_ENV, None)
        else:
            os.environ[SELECTOR_ENV] = before


def resolve_selector(mode: str, k: int, *, jev_client: Any | None = None) -> tuple[Any | None, str]:
    """`(selector, etiqueta)`: `heuristic` → None; `jev`/`auto` → `JevSelector` si Jev está disponible
    (con `jev` se avisa si no), si no heurística."""
    from tutor.selector_jev import API_KEY_ENV, JevSelector

    mode = (mode or "auto").strip().lower()
    if mode not in SELECTOR_MODES:
        raise ValueError(f"selector desconocido: {mode!r} (válidos: {', '.join(SELECTOR_MODES)})")
    if mode == "heuristic":
        return None, "heuristic"
    selector = JevSelector(client=jev_client, k=k)
    if selector.client is None:
        if mode == "jev":
            log.warning("--selector jev pero Jev no está disponible (falta %s o el SDK): heurística", API_KEY_ENV)
        return None, "heuristic"
    return selector, "jev"


def default_model() -> str:
    return os.environ.get("TUTOR_MODEL") or "test"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


# --------------------------------------------------------------------------------------------
# Una pregunta → un registro
# --------------------------------------------------------------------------------------------

#: Reintentos por pregunta ante errores transitorios del proveedor (OpenRouter reserva
#: `max_tokens` contra el crédito y devuelve 402 `in_flight_budget_exhausted` con Retry-After).
DEFAULT_RETRIES = 2
DEFAULT_RETRY_WAIT = 30
_TRANSIENT = re.compile(r"status_code: (402|408|429|5\d\d)\b|in_flight|rate.?limit|overloaded|timed? ?out", re.IGNORECASE)
_RETRY_AFTER = re.compile(r"Retry-After'?:?\s*'?(\d+)")


def _first_line(exc: BaseException) -> str:
    text = str(exc)
    return text.splitlines()[0][:400] if text else type(exc).__name__


def _retry_after(exc: BaseException) -> int | None:
    """Segundos a esperar si el error parece transitorio (Retry-After si viene); None si no lo es."""
    text = str(exc)
    if not _TRANSIENT.search(text):
        return None
    match = _RETRY_AFTER.search(text)
    return max(1, min(int(match.group(1)), 300)) if match else DEFAULT_RETRY_WAIT


def evaluate_question(
    question: EvalQuestion,
    *,
    kb: Any,
    model: str,
    selector: Any | None,
    selector_label: str,
    k: int,
    grounder: Grounder | None,
    known_ids: set[str],
    atom_tags: dict[str, list[str]],
    role: str = "tutor",
    retries: int = DEFAULT_RETRIES,
) -> dict[str, Any]:
    """Corre `answer()` y mide retrieval, citas, groundedness y respuesta. Un error transitorio del
    proveedor (402 in-flight budget, 429, 5xx) se reintenta hasta `retries` veces esperando el
    `Retry-After`; cualquier otro queda en `error` y no tumba la corrida."""
    from tutor.agent import answer

    record: dict[str, Any] = {**question.to_dict(), "model": model, "selector": selector_label}
    start = time.perf_counter()
    attempts = 0
    while True:
        attempts += 1
        try:
            with _selector_env("heuristic" if selector is None else "jev"):
                turn = answer(question.question, kb=kb, model=model, role=role, selector=selector, k=k)
            break
        except Exception as exc:  # noqa: BLE001 — una pregunta fallida se reporta, el resto sigue
            wait = _retry_after(exc)
            if wait is not None and attempts <= retries:
                log.warning("%s: %s; reintento %d/%d en %ds", question.id, _first_line(exc), attempts, retries, wait)
                time.sleep(wait)
                start = time.perf_counter()
                continue
            log.warning("%s falló: %s", question.id, exc)
            record.update({"error": f"{type(exc).__name__}: {_first_line(exc)}", "attempts": attempts, "latency_ms": round((time.perf_counter() - start) * 1000, 1)})
            return record
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    mesa = turn.mesa
    reads = list(mesa.get("reads") or [])
    citations = citation_metrics(turn.reply, mesa_ids=mesa["atom_ids"], known_ids=known_ids, expected_ids=question.expected_atom_ids, reads=reads)
    usage = turn.usage or {}
    record.update(
        {
            "reply": turn.reply,
            "mesa": mesa,
            "retrieval": {**retrieval_metrics(mesa["atom_ids"], question, k, atom_tags), **mesa_nouls(mesa)},
            "citations": citations,
            "groundedness": grounder.check(turn.reply, kb) if grounder is not None else {"status": "skipped", "reason": "sin grounder", "n_claims": None, "n_supported": None, "fraction_supported": None, "claims": [], "unsupported": []},
            "answer": {
                "chars": len(turn.reply),
                "words": len(turn.reply.split()),
                "n_citations": citations["n_cited"],
                "latency_ms": latency_ms,
                "requests": usage.get("requests"),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "cost_usd": usage.get("cost_usd"),
                "reads": reads,
            },
        }
    )
    return record


# --------------------------------------------------------------------------------------------
# La corrida completa
# --------------------------------------------------------------------------------------------


def _mean(values: Iterable[float | None]) -> float | None:
    xs = [float(v) for v in values if v is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def summarize(records: list[dict[str, Any]], k: int) -> dict[str, Any]:
    """Promedios sobre las preguntas respondidas: retrieval, citas, groundedness y respuesta."""
    ok = [r for r in records if "error" not in r]
    scored = [r for r in ok if r["retrieval"]["scored"]]
    claims = sum(r["groundedness"].get("n_claims") or 0 for r in ok if r["groundedness"]["status"] == "ok")
    supported = sum(r["groundedness"].get("n_supported") or 0 for r in ok if r["groundedness"]["status"] == "ok")
    statuses = {r["groundedness"]["status"] for r in ok}
    costs = [r["answer"]["cost_usd"] for r in ok if r["answer"]["cost_usd"] is not None]
    return {
        "n_questions": len(records),
        "n_ok": len(ok),
        "n_errors": len(records) - len(ok),
        "retrieval": {
            "n_scored": len(scored),
            "hit@1": _mean(r["retrieval"]["hit@1"] for r in scored),
            f"hit@{k}": _mean(r["retrieval"]["hit@k"] for r in scored),
            "mrr": _mean(r["retrieval"]["rr"] for r in scored),
            f"tag_hit@{k}": _mean(r["retrieval"]["tag_hit@k"] for r in scored),
            "max_noul_mean": _mean(r["retrieval"]["max_noul"] for r in ok),
            "max_noul_min": min((r["retrieval"]["max_noul"] for r in ok if r["retrieval"]["max_noul"] is not None), default=None),
        },
        "citations": {
            "n_cited_mean": _mean(r["citations"]["n_cited"] for r in ok),
            "valid_rate": _mean(r["citations"]["valid_rate"] for r in ok),
            "in_mesa_rate": _mean(r["citations"]["in_mesa_rate"] for r in ok),
            "n_invalid_total": sum(len(r["citations"]["invalid"]) for r in ok),
            "n_out_of_mesa_total": sum(len(r["citations"]["out_of_mesa"]) for r in ok),
            "coverage": _mean(r["citations"]["coverage"] for r in ok),
            "n_without_citations": sum(1 for r in ok if r["citations"]["n_cited"] == 0),
        },
        "groundedness": {
            "status": "ok" if "ok" in statuses else ("skipped" if statuses else "n/a"),
            "n_claims": claims,
            "n_supported": supported,
            "fraction_supported": round(supported / claims, 4) if claims else None,
            "per_question_mean": _mean(r["groundedness"]["fraction_supported"] for r in ok),
        },
        "answer": {
            "chars_mean": _mean(r["answer"]["chars"] for r in ok),
            "words_mean": _mean(r["answer"]["words"] for r in ok),
            "latency_ms_mean": _mean(r["answer"]["latency_ms"] for r in ok),
            "latency_ms_max": max((r["answer"]["latency_ms"] for r in ok), default=None),
            "input_tokens_total": sum(r["answer"]["input_tokens"] or 0 for r in ok),
            "output_tokens_total": sum(r["answer"]["output_tokens"] or 0 for r in ok),
            "requests_mean": _mean(r["answer"]["requests"] for r in ok),
            "cost_usd_total": round(sum(costs), 5) if costs else None,
        },
    }


def run_eval(
    *,
    kb: Any,
    questions: list[EvalQuestion],
    model: str | None = None,
    selector: str = "auto",
    k: int = 8,
    limit: int | None = None,
    role: str = "tutor",
    jev_client: Any | None = None,
    grounder: Grounder | None = None,
    progress: Callable[[str], None] | None = None,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, Any]:
    """Toda la evaluación: `{meta, summary, questions}`. `jev_client` sirve para el selector y para
    la groundedness (si no viene `grounder`); con `FakeJevClient` corre sin red."""
    model = model or default_model()
    if limit:
        questions = questions[:limit]
    sel, sel_label = resolve_selector(selector, k, jev_client=jev_client)
    grounder = grounder or Grounder(client=jev_client)
    known_ids = {a["id"] for a in world.list_atoms(kb)}
    atom_tags = {a["id"]: a["tags"] for a in world.list_atoms(kb)}
    unknown = sorted({e for q in questions for e in q.expected_atom_ids if e not in known_ids})
    started = datetime.now()
    records = []
    for i, q in enumerate(questions, 1):
        if progress:
            progress(f"[{i}/{len(questions)}] {q.id}")
        records.append(evaluate_question(q, kb=kb, model=model, selector=sel, selector_label=sel_label, k=k, grounder=grounder, known_ids=known_ids, atom_tags=atom_tags, role=role, retries=retries))
    summary = summarize(records, k)
    return {
        "meta": {
            "kb": getattr(kb, "name", None),
            "kb_fingerprint": getattr(kb, "fingerprint", None),
            "model": model,
            "selector": sel_label,
            "selector_requested": selector,
            "k": k,
            "role": role,
            "n_questions": len(questions),
            "unknown_expected_ids": unknown,
            "groundedness": summary["groundedness"]["status"],
            "started": started.isoformat(timespec="seconds"),
            "duration_s": round((datetime.now() - started).total_seconds(), 1),
        },
        "summary": summary,
        "questions": records,
    }


def out_dir_for(results: dict[str, Any], base: Path | None = None) -> Path:
    meta = results["meta"]
    stamp = datetime.fromisoformat(meta["started"]).strftime("%Y%m%d-%H%M%S")
    return (base or evals_dir_default()) / f"{stamp}-{_slug(meta['model'])}-{meta['selector']}"


def write_run(results: dict[str, Any], out: Path) -> Path:
    """`results.json` + `report.md` en `out`; devuelve `out`."""
    out.mkdir(parents=True, exist_ok=True)
    (out / RESULTS_FILE).write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / REPORT_FILE).write_text(render_report(results), encoding="utf-8")
    return out


def load_run(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    file = path / RESULTS_FILE if path.is_dir() else path
    return json.loads(file.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------
# Reportes
# --------------------------------------------------------------------------------------------


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "–"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def summary_rows(results: dict[str, Any]) -> list[tuple[str, Any]]:
    """`(métrica, valor)` del resumen, en el orden del reporte."""
    s, k = results["summary"], results["meta"]["k"]
    r, c, g, a = s["retrieval"], s["citations"], s["groundedness"], s["answer"]
    return [
        ("preguntas (ok/errores)", f"{s['n_ok']}/{s['n_errors']}"),
        ("hit@1", r["hit@1"]),
        (f"hit@{k}", r[f"hit@{k}"]),
        ("MRR", r["mrr"]),
        (f"tag_hit@{k}", r[f"tag_hit@{k}"]),
        ("max noul medio (Jev)", r["max_noul_mean"]),
        ("max noul mínimo (Jev)", r["max_noul_min"]),
        ("citas por respuesta", c["n_cited_mean"]),
        ("citas válidas (tasa)", c["valid_rate"]),
        ("citas en mesa (tasa)", c["in_mesa_rate"]),
        ("ids inventados (total)", c["n_invalid_total"]),
        ("citas fuera de mesa (total)", c["n_out_of_mesa_total"]),
        ("coverage de expected", c["coverage"]),
        ("respuestas sin citas", c["n_without_citations"]),
        ("groundedness", g["status"]),
        ("oraciones respaldadas", f"{g['n_supported']}/{g['n_claims']}" if g["n_claims"] else "–"),
        ("fracción respaldada", g["fraction_supported"]),
        ("chars por respuesta", a["chars_mean"]),
        ("latencia media (ms)", a["latency_ms_mean"]),
        ("latencia máx (ms)", a["latency_ms_max"]),
        ("tokens in/out (total)", f"{a['input_tokens_total']}/{a['output_tokens_total']}"),
        ("costo USD (total)", a["cost_usd_total"]),
    ]


def worst_questions(results: dict[str, Any], n: int = 3) -> list[dict[str, Any]]:
    """Las peor respondidas: puntaje = rr + coverage + groundedness (−1 por error / ids inventados)."""
    scored = []
    for r in results["questions"]:
        if "error" in r:
            scored.append((-1.0, r["id"], f"error: {r['error']}"))
            continue
        rr = r["retrieval"]["rr"] if r["retrieval"]["scored"] else 0.5
        cov = r["citations"]["coverage"] if r["citations"]["coverage"] is not None else 0.5
        gr = r["groundedness"]["fraction_supported"]
        gr = 0.5 if gr is None else gr
        penalty = 1.0 if (r["citations"]["invalid"] or r["citations"]["out_of_mesa"]) else 0.0
        score = rr + cov + gr - penalty
        why = []
        if r["retrieval"]["scored"] and not r["retrieval"]["hit@k"]:
            why.append("ningún expected en la mesa")
        elif r["retrieval"]["scored"] and r["retrieval"]["first_hit_rank"] not in (None, 1):
            why.append(f"primer expected en posición {r['retrieval']['first_hit_rank']}")
        if r["citations"]["coverage"] is not None and r["citations"]["coverage"] < 1:
            missing = [e for e in r["expected_atom_ids"] if e not in r["citations"]["cited"]]
            why.append(f"no cita {', '.join(missing)}")
        if r["citations"]["invalid"]:
            why.append(f"ids inventados: {', '.join(r['citations']['invalid'])}")
        if r["citations"]["out_of_mesa"]:
            why.append(f"cita fuera de mesa: {', '.join(r['citations']['out_of_mesa'])}")
        if r["citations"]["n_cited"] == 0:
            why.append("sin citas")
        if r["groundedness"]["status"] == "ok" and r["groundedness"]["unsupported"]:
            why.append(f"{len(r['groundedness']['unsupported'])} oración(es) no respaldada(s)")
        if r["retrieval"].get("max_noul") is not None and r["retrieval"]["max_noul"] < 0.5:
            why.append(f"max noul {r['retrieval']['max_noul']:.2f}: la KB cubre poco")
        scored.append((score, r["id"], "; ".join(why) or "sin problemas detectados"))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [{"id": qid, "score": round(score, 3), "why": why} for score, qid, why in scored[:n]]


def render_report(results: dict[str, Any]) -> str:
    """El `report.md`: cabecera, resumen, tabla por pregunta, peores preguntas y oraciones sin respaldo."""
    meta, k = results["meta"], results["meta"]["k"]
    lines = [
        f"# Eval del tutor · {meta['model']} · selector {meta['selector']}",
        "",
        f"KB `{meta['kb']}` · k={k} · {meta['n_questions']} preguntas · {meta['started']} · {meta['duration_s']} s · groundedness: {meta['groundedness']}",
    ]
    if meta.get("unknown_expected_ids"):
        lines.append(f"\n> expected ids que no existen en la KB: {', '.join(meta['unknown_expected_ids'])}")
    lines += ["", "## Resumen", "", _md_table(["métrica", "valor"], [[name, _fmt(value)] for name, value in summary_rows(results)])]
    rows = []
    for r in results["questions"]:
        if "error" in r:
            rows.append([r["id"], *(["–"] * 9), _fmt(r.get("latency_ms")), f"error: {r['error']}"])
            continue
        rt, c, g, a = r["retrieval"], r["citations"], r["groundedness"], r["answer"]
        grounded = f"{g['n_supported']}/{g['n_claims']}" if g["status"] == "ok" and g["n_claims"] else ("–" if g["status"] != "ok" else "0/0")
        rows.append([
            r["id"], _fmt(rt["hit@1"]), _fmt(rt["hit@k"]), _fmt(rt["rr"]), _fmt(rt.get("max_noul")),
            c["n_cited"], f"{len(c['valid'])}/{c['n_cited']}" if c["n_cited"] else "0", f"{len(c['in_mesa'])}/{len(c['valid'])}" if c["valid"] else "–",
            _fmt(c["coverage"]), grounded, _fmt(a["latency_ms"], 0), f"{a['input_tokens'] or 0}/{a['output_tokens'] or 0}",
        ])
    lines += ["", "## Por pregunta", "", _md_table(["id", "hit@1", f"hit@{k}", "rr", "max noul", "citas", "válidas", "en mesa", "coverage", "respaldadas", "ms", "tok in/out"], rows)]
    lines += ["", "## Peores preguntas", ""]
    lines += [f"- **{w['id']}** ({w['score']}): {w['why']}" for w in worst_questions(results)]
    unsupported = [(r["id"], u) for r in results["questions"] if "error" not in r for u in r["groundedness"].get("unsupported") or []]
    if unsupported:
        lines += ["", "## Oraciones no respaldadas por el átomo citado", ""]
        lines += [f"- **{qid}** (noul {u['noul']:.2f}, cita {', '.join(u['atom_ids'])}): {u['sentence']}" for qid, u in unsupported]
    return "\n".join(lines) + "\n"


def render_summary_text(results: dict[str, Any]) -> str:
    meta = results["meta"]
    lines = [f"eval · {meta['model']} · selector {meta['selector']} · k={meta['k']} · {meta['n_questions']} preguntas · {meta['duration_s']} s"]
    width = max(len(name) for name, _ in summary_rows(results))
    lines += [f"  {name.ljust(width)}  {_fmt(value)}" for name, value in summary_rows(results)]
    lines.append("  peores:")
    lines += [f"    {w['id']}: {w['why']}" for w in worst_questions(results)]
    return "\n".join(lines)


def compare_runs(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Markdown con el resumen de A y B lado a lado (y delta) y las métricas clave por pregunta."""
    la = f"{a['meta']['model']} · {a['meta']['selector']}"
    lb = f"{b['meta']['model']} · {b['meta']['selector']}"
    rows = []
    for (name, va), (_, vb) in zip(summary_rows(a), summary_rows(b)):
        delta = f"{vb - va:+.3f}" if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and not isinstance(va, bool) else ""
        rows.append([name, _fmt(va), _fmt(vb), delta])
    out = [f"# Comparación · A = {la} · B = {lb}", "", _md_table(["métrica", "A", "B", "B−A"], rows)]
    qa = {r["id"]: r for r in a["questions"]}
    qb = {r["id"]: r for r in b["questions"]}

    def cell(r: dict[str, Any] | None, key: tuple[str, str]) -> str:
        if r is None or "error" in r:
            return "err" if r else "–"
        return _fmt(r[key[0]].get(key[1]))

    per = []
    for qid in [i for i in qa if i in qb] + [i for i in qb if i not in qa]:
        ra, rb = qa.get(qid), qb.get(qid)
        per.append([
            qid,
            f"{cell(ra, ('retrieval', 'hit@k'))}/{cell(rb, ('retrieval', 'hit@k'))}",
            f"{cell(ra, ('retrieval', 'rr'))}/{cell(rb, ('retrieval', 'rr'))}",
            f"{cell(ra, ('citations', 'coverage'))}/{cell(rb, ('citations', 'coverage'))}",
            f"{cell(ra, ('groundedness', 'fraction_supported'))}/{cell(rb, ('groundedness', 'fraction_supported'))}",
            f"{cell(ra, ('answer', 'latency_ms'))}/{cell(rb, ('answer', 'latency_ms'))}",
        ])
    out += ["", "## Por pregunta (A/B)", "", _md_table(["id", "hit@k", "rr", "coverage", "respaldada", "ms"], per)]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------------
# Un turno explicado
# --------------------------------------------------------------------------------------------


def find_question(question: str, questions: list[EvalQuestion]) -> EvalQuestion | None:
    """La pregunta del YAML cuyo id o texto (normalizado) coincide con `question`."""
    wanted = _norm_title(question)
    for q in questions:
        if q.id == question.strip() or _norm_title(q.question) == wanted:
            return q
    return None


def explain_turn(
    question: str,
    *,
    kb: Any,
    model: str | None = None,
    selector: str = "auto",
    k: int = 8,
    questions: list[EvalQuestion] | None = None,
    jev_client: Any | None = None,
    grounder: Grounder | None = None,
    role: str = "tutor",
) -> dict[str, Any]:
    """Un turno con todo a la vista: mesa (why/noul), expected del YAML si la pregunta está, qué citó
    y qué no, groundedness por oración. Mismo registro que `run` para una pregunta."""
    known = questions if questions is not None else _safe_load_questions()
    q = find_question(question, known) or EvalQuestion("turn", question)
    results = run_eval(kb=kb, questions=[q], model=model, selector=selector, k=k, role=role, jev_client=jev_client, grounder=grounder)
    record = results["questions"][0]
    record["in_benchmark"] = q.id != "turn"
    record["meta"] = results["meta"]
    if "error" not in record:
        expected = set(q.expected_atom_ids)
        record["mesa_view"] = [
            {**{key: item[key] for key in ("atom_id", "title", "score", "role", "why")}, "expected": item["atom_id"] in expected, "cited": item["atom_id"] in record["citations"]["cited"]}
            for item in record["mesa"]["items"]
        ]
        record["expected_missing_from_mesa"] = [e for e in q.expected_atom_ids if e not in record["mesa"]["atom_ids"]]
    return record


#: Alias para la tool MCP homónima, que sombrea el nombre dentro de `register_mcp`.
_explain_turn = explain_turn


def _safe_load_questions() -> list[EvalQuestion]:
    try:
        return load_questions()
    except (OSError, ImportError, KeyError):
        return []


def render_turn(record: dict[str, Any]) -> str:
    meta = record.get("meta", {})
    lines = [f"pregunta: {record['question']}", f"modelo {meta.get('model')} · selector {meta.get('selector')} · k={meta.get('k')}" + (f" · benchmark {record['id']}" if record.get("in_benchmark") else " · no está en el YAML")]
    if "error" in record:
        return "\n".join([*lines, f"ERROR: {record['error']}"])
    lines += ["", "mesa (score = noul si el selector fue Jev):"]
    for item in record["mesa_view"]:
        marks = ("E" if item["expected"] else " ") + ("C" if item["cited"] else " ")
        lines.append(f"  {marks} {item['score']:.3f} {item['role']:<9} {item['atom_id']}  ({item['why']})")
    lines.append("  E = expected · C = citado")
    if record["expected_atom_ids"]:
        lines.append(f"expected: {', '.join(record['expected_atom_ids'])}")
        if record["expected_missing_from_mesa"]:
            lines.append(f"  NO entraron a la mesa: {', '.join(record['expected_missing_from_mesa'])}")
    rt = record["retrieval"]
    if rt["scored"]:
        lines.append(f"retrieval: hit@1={rt['hit@1']} hit@k={rt['hit@k']} rr={rt['rr']:.2f} max_noul={_fmt(rt.get('max_noul'))}")
    if record["answer"]["reads"]:
        lines.append(f"leídos con show_atom: {', '.join(record['answer']['reads'])}")
    c = record["citations"]
    lines += ["", f"citas: {c['n_cited']} · válidas {len(c['valid'])} · en mesa {len(c['in_mesa'])} · fuera de mesa {len(c['out_of_mesa'])} · inventadas {len(c['invalid'])} · coverage {_fmt(c['coverage'])}"]
    if c["invalid"]:
        lines.append(f"  inventadas: {', '.join(c['invalid'])}")
    if c["out_of_mesa"]:
        lines.append(f"  fuera de mesa: {', '.join(c['out_of_mesa'])}")
    missing = [e for e in record["expected_atom_ids"] if e not in c["cited"]]
    if missing:
        lines.append(f"  expected no citados: {', '.join(missing)}")
    g = record["groundedness"]
    lines += ["", f"groundedness: {g['status']}" + (f" · {g['n_supported']}/{g['n_claims']} oraciones respaldadas (umbral {g['threshold']})" if g["status"] == "ok" else f" ({g.get('reason', '')})")]
    for claim in g.get("claims") or []:
        mark = "ok " if claim["supported"] else "NO "
        lines.append(f"  [{mark}{claim['noul']:.2f}] {claim['sentence']}")
    a = record["answer"]
    lines += ["", f"respuesta: {a['chars']} chars · {a['n_citations']} citas · {a['latency_ms']:.0f} ms · tokens {a['input_tokens']}/{a['output_tokens']}", "", record["reply"]]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------
# Salud de la KB
# --------------------------------------------------------------------------------------------

_TITLE_STOP = frozenset("el la los las un una unos unas de del al en y o a que es son se por para con como su sus the of and in".split())


def _norm_title(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()
    words = [w for w in re.findall(r"[a-z0-9]+", text) if w not in _TITLE_STOP]
    return " ".join(words)


def _jaccard(a: str, b: str) -> float:
    """Jaccard de las palabras de dos títulos normalizados (sin stopwords)."""
    sa, sb = set(a.split()), set(b.split())
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def usage_from_evals(evals_dir: Path | str | None) -> dict[str, Any]:
    """Cuántas veces entró cada átomo a una mesa y cuántas fue citado, sumando `*/results.json`."""
    base = Path(evals_dir) if evals_dir else evals_dir_default()
    in_mesa: dict[str, int] = {}
    cited: dict[str, int] = {}
    runs = sorted(base.glob(f"*/{RESULTS_FILE}")) if base.is_dir() else []
    for file in runs:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in data.get("questions", []):
            for atom_id in (r.get("mesa") or {}).get("atom_ids") or []:
                in_mesa[atom_id] = in_mesa.get(atom_id, 0) + 1
            for atom_id in (r.get("citations") or {}).get("valid") or []:
                cited[atom_id] = cited.get(atom_id, 0) + 1
    return {"dir": str(base), "n_runs": len(runs), "in_mesa": in_mesa, "cited": cited}


def atoms_health(
    kb: Any,
    evals_dir: Path | str | None = None,
    *,
    short_chars: int = SHORT_ANSWER_CHARS,
    long_chars: int = LONG_ANSWER_CHARS,
    dup_ratio: float = DUP_TITLE_RATIO,
    embed_sim: float = DUP_EMBED_SIM,
) -> dict[str, Any]:
    """Diagnóstico de la KB: sin provenance, respuestas cortas/largas, títulos casi duplicados,
    tags sin namespace declarado, ramas sin hojas, huérfanos y —con corridas en `evals_dir`— uso."""
    from tutor.embedding import HashEmbedder

    atoms = world.list_atoms(kb)
    branches = world.list_branches(kb)
    atom_ids = {a["id"] for a in atoms}
    namespaces = {str(d.payload.get("tag")) for d in kb.by_model("TagNamespaceDoc")}

    no_provenance = [a["id"] for a in atoms if not str(a.get("provenance") or "").strip()]
    short = [{"id": a["id"], "chars": len(str(a["summary"]).strip())} for a in atoms if len(str(a["summary"]).strip()) < short_chars]
    long_ = [{"id": a["id"], "chars": len(str(a["summary"]).strip())} for a in atoms if len(str(a["summary"]).strip()) > long_chars]

    normalized = {a["id"]: _norm_title(a["title"]) for a in atoms}
    vectors = dict(zip([a["id"] for a in atoms], HashEmbedder().embed([a["title"] for a in atoms]))) if atoms else {}
    duplicates = []
    ordered = sorted(atoms, key=lambda a: a["id"])
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            na, nb = normalized[a["id"]], normalized[b["id"]]
            ratio = _jaccard(na, nb)
            sim = _cosine(vectors[a["id"]], vectors[b["id"]])
            signals = []
            if na and na == nb:
                signals.append("title_equal")
            elif ratio >= dup_ratio:
                signals.append(f"title_jaccard:{ratio:.2f}")
            if sim >= embed_sim:
                signals.append(f"embed_sim:{sim:.2f}")
            if signals:
                duplicates.append({"a": a["id"], "b": b["id"], "title_a": a["title"], "title_b": b["title"], "ratio": round(ratio, 3), "embed_sim": round(sim, 3), "signals": signals})

    bad_tags = []
    for a in atoms:
        for tag in a["tags"]:
            ns, sep, _ = str(tag).partition(":")
            if not sep or ns not in namespaces:
                bad_tags.append({"id": a["id"], "tag": tag, "reason": "sin namespace" if not sep else f"namespace no declarado: {ns}"})

    kids = {b["id"]: world.children(kb, b["id"]) for b in branches}

    def has_atoms(branch_id: str, seen: set[str]) -> bool:
        if branch_id in seen:
            return False
        seen.add(branch_id)
        return any(c["id"] in atom_ids or (c["id"] in kids and has_atoms(c["id"], seen)) for c in kids.get(branch_id, []))

    empty_branches = [{"id": b["id"], "title": b["title"], "n_children": len(kids[b["id"]]), "has_atoms_below": has_atoms(b["id"], set())} for b in branches if not has_atoms(b["id"], set())]
    orphans = [a["id"] for a in atoms if world.parent(kb, a["id"]) is None]
    dangling_parent = [{"id": a["id"], "parent": a["parent"]} for a in atoms if a.get("parent") and world.get_atom(kb, str(a["parent"])) is None]

    usage = usage_from_evals(evals_dir)
    never_used = sorted(a for a in atom_ids if not usage["in_mesa"].get(a) and not usage["cited"].get(a)) if usage["n_runs"] else []
    most_used = sorted(({"id": a, "in_mesa": usage["in_mesa"].get(a, 0), "cited": usage["cited"].get(a, 0)} for a in atom_ids), key=lambda u: (-u["cited"], -u["in_mesa"], u["id"]))[:10] if usage["n_runs"] else []

    return {
        "kb": getattr(kb, "name", None),
        "n_atoms": len(atoms),
        "n_branches": len(branches),
        "thresholds": {"short_chars": short_chars, "long_chars": long_chars, "dup_ratio": dup_ratio, "embed_sim": embed_sim},
        "no_provenance": no_provenance,
        "short_answers": short,
        "long_answers": long_,
        "near_duplicate_titles": duplicates,
        "undeclared_tags": bad_tags,
        "declared_namespaces": sorted(namespaces),
        "branches_without_atoms": empty_branches,
        "orphan_atoms": orphans,
        "dangling_parent": dangling_parent,
        "usage": {"dir": usage["dir"], "n_runs": usage["n_runs"], "never_in_mesa_nor_cited": never_used, "most_used": most_used, "n_in_mesa": sum(1 for a in atom_ids if usage["in_mesa"].get(a)), "n_cited": sum(1 for a in atom_ids if usage["cited"].get(a))},
        "counts": {
            "no_provenance": len(no_provenance),
            "short_answers": len(short),
            "long_answers": len(long_),
            "near_duplicate_titles": len(duplicates),
            "undeclared_tags": len(bad_tags),
            "branches_without_atoms": len(empty_branches),
            "orphan_atoms": len(orphans),
            "dangling_parent": len(dangling_parent),
            "never_used": len(never_used),
        },
    }


def render_health(report: dict[str, Any], *, limit: int = 15) -> str:
    c = report["counts"]
    lines = [f"KB {report['kb']} · {report['n_atoms']} átomos · {report['n_branches']} ramas", "", f"{'chequeo':<28}{'n':>5}"]
    labels = [
        ("sin provenance", "no_provenance"), (f"respuesta < {report['thresholds']['short_chars']} chars", "short_answers"),
        (f"respuesta > {report['thresholds']['long_chars']} chars", "long_answers"), ("títulos casi duplicados", "near_duplicate_titles"),
        ("tags sin namespace", "undeclared_tags"), ("ramas sin átomos", "branches_without_atoms"), ("átomos huérfanos", "orphan_atoms"),
        ("parent inexistente", "dangling_parent"), ("nunca en mesa ni citados", "never_used"),
    ]
    lines += [f"{label:<28}{c[key]:>5}" for label, key in labels]

    def section(title: str, items: list[str]) -> None:
        if items:
            lines.extend(["", f"{title}:"] + [f"  {x}" for x in items[:limit]] + ([f"  … {len(items) - limit} más"] if len(items) > limit else []))

    section("sin provenance", report["no_provenance"])
    section("respuestas cortas", [f"{s['id']} ({s['chars']} chars)" for s in report["short_answers"]])
    section("respuestas largas", [f"{s['id']} ({s['chars']} chars)" for s in report["long_answers"]])
    section("títulos casi duplicados", [f"{d['a']} ~ {d['b']} [{', '.join(d['signals'])}]" for d in report["near_duplicate_titles"]])
    section("tags sin namespace declarado", [f"{t['id']}: {t['tag']} ({t['reason']})" for t in report["undeclared_tags"]])
    section("ramas sin átomos debajo", [f"{b['id']} ({b['n_children']} hijos directos)" for b in report["branches_without_atoms"]])
    section("átomos huérfanos (sin child_of)", report["orphan_atoms"])
    section("parent inexistente", [f"{d['id']} → {d['parent']}" for d in report["dangling_parent"]])
    u = report["usage"]
    if u["n_runs"]:
        lines += ["", f"uso en {u['n_runs']} corrida(s) de {u['dir']}: {u['n_in_mesa']} átomos entraron a alguna mesa, {u['n_cited']} fueron citados"]
        section("nunca en mesa ni citados (revisar)", u["never_in_mesa_nor_cited"])
        section("más usados (citado/en mesa)", [f"{m['id']}  {m['cited']}/{m['in_mesa']}" for m in u["most_used"]])
    else:
        lines += ["", f"sin corridas en {u['dir']}: corre `tutor eval run` para medir uso"]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------
# CLI (`tutor eval …`)
# --------------------------------------------------------------------------------------------


# Con `from __future__ import annotations` typer resuelve las anotaciones en el módulo: los alias
# viven aquí, no dentro de `register_cli`.
KbOpt = Annotated[Path | None, typer.Option("--kb", help="Raíz de la KB; por defecto TUTOR_KB o kbs/apos.")]
ModelOpt = Annotated[str | None, typer.Option("--model", help="test | provider:model; por defecto TUTOR_MODEL o test.")]
SelectorOpt = Annotated[str, typer.Option("--selector", help="auto | heuristic | jev.")]
KOpt = Annotated[int, typer.Option("--k", help="Tamaño de la mesa.")]
QuestionsOpt = Annotated[Path | None, typer.Option("--questions", help="YAML con `questions:`; por defecto benchmarks/apos_questions.yaml.")]
LimitOpt = Annotated[int | None, typer.Option("--limit", help="Solo las primeras N preguntas.")]
OutOpt = Annotated[Path | None, typer.Option("--out", help="Dir de salida; por defecto runs/evals/<ts>-<modelo>-<selector>/.")]
RunDirArg = Annotated[Path, typer.Argument(help="Dir con results.json.")]
MdOpt = Annotated[bool, typer.Option("--md", help="Imprimir el report.md completo.")]
QuestionArg = Annotated[str, typer.Argument(help="La pregunta (o un id del YAML, p. ej. q05-encapsulacion).")]
JsonFlag = Annotated[bool, typer.Option("--json")]
EvalsOpt = Annotated[Path | None, typer.Option("--evals", help="Dir con corridas (runs/evals/) para medir uso.")]
JsonOutOpt = Annotated[Path | None, typer.Option("--json", help="Escribir el JSON completo aquí.")]


def register_cli(app: Any) -> None:
    """Suma el sub-typer `eval` a `tutor.cli.app`."""
    eval_app = typer.Typer(help="Evaluar al tutor (razonamiento) y a la KB (átomos).", no_args_is_help=True)

    @eval_app.command("run")
    def run_cmd(
        kb: KbOpt = None,
        questions: QuestionsOpt = None,
        model: ModelOpt = None,
        selector: SelectorOpt = "auto",
        k: KOpt = 8,
        limit: LimitOpt = None,
        out: OutOpt = None,
    ) -> None:
        """Corre el tutor sobre las preguntas y mide retrieval, citas, groundedness (Jev) y respuesta."""
        opened = world.open_kb(kb)
        results = run_eval(kb=opened, questions=load_questions(questions), model=model, selector=selector, k=k, limit=limit, progress=lambda m: typer.echo(m, err=True))
        where = write_run(results, out or out_dir_for(results))
        typer.echo(render_summary_text(results))
        typer.echo(f"\nresultados en {where}")

    @eval_app.command("report")
    def report_cmd(run_dir: RunDirArg, markdown: MdOpt = False) -> None:
        """Reimprime el resumen (o el report.md) de una corrida."""
        results = load_run(run_dir)
        typer.echo(render_report(results) if markdown else render_summary_text(results))

    @eval_app.command("compare")
    def compare_cmd(a: RunDirArg, b: RunDirArg) -> None:
        """Compara dos corridas (heuristic vs jev, dos modelos…): resumen con delta y por pregunta."""
        typer.echo(compare_runs(load_run(a), load_run(b)))

    @eval_app.command("turn")
    def turn_cmd(
        question: QuestionArg,
        kb: KbOpt = None,
        model: ModelOpt = None,
        selector: SelectorOpt = "auto",
        k: KOpt = 8,
        questions: QuestionsOpt = None,
        as_json: JsonFlag = False,
    ) -> None:
        """Explica UN turno: mesa con why/noul, qué citó y qué no, groundedness por oración, expected."""
        known = load_questions(questions) if questions else _safe_load_questions()
        record = explain_turn(question, kb=world.open_kb(kb), model=model, selector=selector, k=k, questions=known)
        typer.echo(json.dumps(record, ensure_ascii=False, indent=2, default=str) if as_json else render_turn(record))

    @eval_app.command("atoms")
    def atoms_cmd(
        kb: KbOpt = None,
        evals: EvalsOpt = None,
        json_out: JsonOutOpt = None,
    ) -> None:
        """Salud de la KB: provenance, longitud, duplicados, tags, ramas vacías, huérfanos y uso en evals."""
        report = atoms_health(world.open_kb(kb), evals)
        typer.echo(render_health(report))
        if json_out:
            json_out.parent.mkdir(parents=True, exist_ok=True)
            json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            typer.echo(f"\nJSON en {json_out}")

    app.add_typer(eval_app, name="eval")


# --------------------------------------------------------------------------------------------
# MCP (`eval_run`, `explain_turn`, `eval_atoms`)
# --------------------------------------------------------------------------------------------


def _compact(record: dict[str, Any]) -> dict[str, Any]:
    """El registro sin la mesa completa ni el reasoning_log (para la respuesta MCP)."""
    out = {key: value for key, value in record.items() if key not in ("mesa", "meta")}
    if "mesa" in record:
        out["mesa_atom_ids"] = record["mesa"].get("atom_ids")
        out["mesa_items"] = [{k_: i[k_] for k_ in ("atom_id", "score", "role", "why")} for i in record["mesa"].get("items", [])]
    return out


class EvalQuestionModel(BaseModel):
    """Una pregunta para `eval_run` por MCP (módulo-level: la SDK resuelve las anotaciones aquí)."""

    question: str = Field(description="La pregunta tal como la haría un estudiante.")
    expected_atom_ids: list[str] = Field(default_factory=list, description="Ids de átomos que cuentan como acierto (puede ir vacío).")
    expected_tags: list[str] = Field(default_factory=list, description="Tags que debería traer algún átomo de la mesa.")
    id: str | None = Field(default=None, description="Etiqueta opcional.")


def register_mcp(server: Any, state: Any, safe: Callable[..., Any], annotations: dict[str, Any]) -> None:
    """Tools de evaluación sobre `tutor.mcp_server`: `eval_run`, `explain_turn`, `eval_atoms`."""
    @server.tool(annotations=annotations["calls_model"])
    @safe
    def eval_run(kb_id: str, questions: list[EvalQuestionModel] | None = None, model: str | None = None, k: int = 8, selector: str = "auto", limit: int | None = None, out: str | None = None) -> dict[str, Any]:
        """Evalúa al tutor sobre `questions` (`[{question, expected_atom_ids}]`; si va vacío y `kb_id` es
        `apos`, usa benchmarks/apos_questions.yaml): por pregunta corre un turno y mide retrieval
        (hit@1/hit@k/MRR, noul máximo si el selector es Jev), citas (válidas, en mesa, coverage),
        groundedness por oración con Jev (skipped sin TYPESAFE_API_KEY) y latencia/tokens. `model` por
        defecto TUTOR_MODEL (`test` no gasta). Con `out` escribe results.json + report.md en ese dir."""
        kb = state.kb(kb_id)
        if questions:
            qs = questions_from(questions)
        elif kb_id == "apos":
            qs = load_questions()
        else:
            raise ValueError("pasa `questions` ([{question, expected_atom_ids}]); solo la KB apos tiene YAML por defecto")
        results = run_eval(kb=kb, questions=qs, model=model, selector=selector, k=k, limit=limit)
        response = {"meta": results["meta"], "summary": results["summary"], "worst": worst_questions(results), "questions": [_compact(r) for r in results["questions"]]}
        if out:
            response["out"] = str(write_run(results, Path(out)))
        return response

    @server.tool(annotations=annotations["calls_model"])
    @safe
    def explain_turn(kb_id: str, question: str, model: str | None = None, selector: str = "auto", k: int = 8) -> dict[str, Any]:
        """Explica UN turno del tutor: la mesa con por qué entró cada átomo (y su noul si el selector fue
        Jev), cuáles eran expected (si la pregunta está en el benchmark de apos), qué citó, qué citó
        fuera de la mesa o inventó, y la groundedness de cada oración citada. Incluye `text` legible."""
        kb = state.kb(kb_id)
        known = _safe_load_questions() if kb_id == "apos" else []
        record = _explain_turn(question, kb=kb, model=model, selector=selector, k=k, questions=known)
        return {**_compact(record), "meta": record.get("meta"), "text": render_turn(record)}

    @server.tool(annotations=annotations["read_only"])
    @safe
    def eval_atoms(kb_id: str, evals_dir: str | None = None) -> dict[str, Any]:
        """Salud de la KB sin LLM: átomos sin provenance, respuestas muy cortas/largas, títulos casi
        duplicados, tags con namespace no declarado, ramas sin átomos, huérfanos, y —si hay corridas en
        `evals_dir` (default runs/evals/)— átomos nunca usados y los más usados. Incluye `text` legible."""
        report = atoms_health(state.kb(kb_id), evals_dir)
        return {**report, "text": render_health(report)}


__all__ = [
    "EvalQuestion",
    "Grounder",
    "atoms_health",
    "citation_metrics",
    "cited_sentences",
    "compare_runs",
    "evaluate_question",
    "explain_turn",
    "extract_citations",
    "load_questions",
    "load_run",
    "register_cli",
    "register_mcp",
    "render_health",
    "render_report",
    "render_turn",
    "resolve_selector",
    "retrieval_metrics",
    "run_eval",
    "split_sentences",
    "summarize",
    "worst_questions",
    "write_run",
]
