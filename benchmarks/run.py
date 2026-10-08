"""Compara métodos de selección de contexto sobre `benchmarks/apos_questions.yaml`.

    python -m benchmarks.run [--methods heuristic,embed,jev,jev_tree] [--k 5] [--out benchmarks/results.json]

Métodos:
- `heuristic`: port del scoring léxico de `apps/kb_agent/runtime/compiler.py` (aliases/expansiones de
  `apps/kb_agent/packs/apos/expansion_rules.json`, tokens, bonus) sobre `world.list_atoms`.
- `embed`: `world.rank(kb, q, k)` (HashEmbedder determinista por defecto, `TUTOR_EMBEDDER=hash`).
- `jev`: top-30 de `embed` → `JevSelector` (Noul por candidato). `jev_tree`: `JevTreeRouter`
  (Choice por nivel, beam K=3). Sin `TYPESAFE_API_KEY` quedan `skipped` con razón.

Métricas por método: hit@1, hit@k, MRR sobre `expected_atom_ids`; tag-hit@k sobre `expected_tags`;
latencia media en ms. Imprime una tabla y escribe el JSON.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

REPO = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = Path(__file__).resolve().parent / "apos_questions.yaml"
EXPANSION_RULES = REPO / "apps" / "kb_agent" / "packs" / "apos" / "expansion_rules.json"
DEFAULT_TAGS = ["system:apos"]  # pack.json del pack apos
ALL_METHODS = ("heuristic", "embed", "jev", "jev_tree")
JEV_POOL = 30

log = logging.getLogger("benchmarks.run")


# --------------------------------------------------------------------------- datos


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    expected_atom_ids: tuple[str, ...]
    expected_tags: tuple[str, ...]


def load_questions(path: Path = QUESTIONS_PATH) -> list[Question]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        Question(q["id"], q["question"], tuple(q["expected_atom_ids"]), tuple(q.get("expected_tags", [])))
        for q in data["questions"]
    ]


# --------------------------------------------------------------------------- heurística (port de MesaCompiler)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text.lower()


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9:-]+", _normalize(text)) if len(t) >= 3}


class HeuristicRanker:
    """Port fiel de `MesaCompiler._extract_tags` + expansiones + `_rank_atoms` (sin turno previo)."""

    def __init__(self, atoms: list[dict[str, Any]], rules_path: Path = EXPANSION_RULES, default_tags: list[str] | None = None):
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
        self.atoms = atoms
        self.aliases: dict[str, list[str]] = rules["aliases"]
        self.expansions: dict[str, list[str]] = rules["expansions"]
        self.scoring: dict[str, int] = rules["scoring"]
        self.default_tags = list(DEFAULT_TAGS if default_tags is None else default_tags)

    def extract_tags(self, query: str) -> list[str]:
        q = _normalize(query)
        tags: list[str] = []
        for alias, mapped in self.aliases.items():
            if _normalize(alias) in q:
                for tag in mapped:
                    if tag not in tags:
                        tags.append(tag)
        return tags

    def rank(self, query: str, k: int) -> list[str]:
        include_tags = self.extract_tags(query)
        for default_tag in self.default_tags:
            if default_tag not in include_tags:
                include_tags.append(default_tag)
        expanded_tags = include_tags[:]
        for tag in include_tags:
            for extra in self.expansions.get(tag, []):
                if extra not in expanded_tags:
                    expanded_tags.append(extra)

        q_tokens = _tokenize(query)
        items: list[tuple[int, str]] = []
        for atom in self.atoms:
            tags = atom.get("tags", [])
            atom_id = atom["id"]
            score = 0
            exact_tag_hits = [t for t in include_tags if t in tags]
            expanded_hits = [t for t in expanded_tags if t in tags and t not in include_tags]
            if exact_tag_hits:
                score += int(self.scoring["exact_tag"]) * len(exact_tag_hits)
            if expanded_hits:
                score += int(self.scoring["expanded_tag"]) * len(expanded_hits)

            haystack = " ".join([
                atom_id,
                atom.get("title", "") or "",
                atom.get("question", "") or "",
                atom.get("summary", "") or "",  # `answer` en el pack viejo
                " ".join(tags),
            ])
            overlap = q_tokens & _tokenize(haystack)
            if overlap:
                score += int(self.scoring["lexical_overlap"]) * len(overlap)

            pedagogy_bonus = int(self.scoring.get("pedagogy_included_bonus", 20))
            pedagogy_penalty = int(self.scoring.get("pedagogy_excluded_penalty", -10))
            theory_bonus = int(self.scoring.get("theory_bonus", 5))
            if "layer:pedagogy" in include_tags and "layer:pedagogy" in tags:
                score += pedagogy_bonus
            elif "layer:pedagogy" not in include_tags and "layer:pedagogy" in tags:
                score += pedagogy_penalty
            if "layer:theory" in tags:
                score += theory_bonus

            if score <= 0:
                continue
            items.append((score, atom_id))
        items.sort(key=lambda x: (-x[0], x[1]))
        return [atom_id for _, atom_id in items[:k]]


# --------------------------------------------------------------------------- métodos


Method = Callable[[str, int], list[str]]


@dataclass
class MethodResult:
    name: str
    status: str = "ok"
    reason: str | None = None
    per_question: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def build_methods(kb: Any, names: list[str], *, jev_threshold: float, jev_client: Any | None = None) -> dict[str, Method | str]:
    """Para cada método, un callable `(question, k) -> ids` o un string con la razón del skip."""
    from tutor import world
    from tutor.selector_jev import API_KEY_ENV, JevSelector, JevTreeRouter

    atoms = world.list_atoms(kb)
    by_id = {a["id"]: a for a in atoms}
    heuristic = HeuristicRanker(atoms)
    methods: dict[str, Method | str] = {}

    def embed(question: str, k: int) -> list[str]:
        return [atom_id for atom_id, _ in world.rank(kb, question, k)]

    needs_jev = any(n in names for n in ("jev", "jev_tree"))
    jev_reason = None
    if needs_jev and jev_client is None and not os.environ.get(API_KEY_ENV):
        jev_reason = f"sin {API_KEY_ENV} en el entorno"

    for name in names:
        if name == "heuristic":
            methods[name] = heuristic.rank
        elif name == "embed":
            methods[name] = embed
        elif name == "jev":
            if jev_reason:
                methods[name] = jev_reason
                continue
            selector = JevSelector(client=jev_client, threshold=jev_threshold, k=JEV_POOL)

            def jev(question: str, k: int, _selector: JevSelector = selector) -> list[str]:
                pool = [(atom_id, f"{by_id[atom_id]['title']}. {by_id[atom_id]['summary']}") for atom_id, _ in world.rank(kb, question, JEV_POOL)]
                chosen = _selector.select("tutor", question, None, pool)
                if chosen is None:
                    raise RuntimeError("JevSelector devolvió None (sin cliente o error de red)")
                return chosen[:k]

            methods[name] = jev
        elif name == "jev_tree":
            if jev_reason:
                methods[name] = jev_reason
                continue
            router = JevTreeRouter(kb, client=jev_client)  # beam K=3: devuelve ≤ 3 hojas

            def jev_tree(question: str, k: int, _router: JevTreeRouter = router) -> list[str]:
                leaves = _router.route(question)
                if leaves is None:
                    raise RuntimeError("JevTreeRouter devolvió None (sin cliente o error de red)")
                return [atom_id for atom_id, _ in leaves[:k]]

            methods[name] = jev_tree
        else:
            raise SystemExit(f"método desconocido: {name} (válidos: {', '.join(ALL_METHODS)})")
    return methods


# --------------------------------------------------------------------------- métricas


def evaluate(method: Method, questions: list[Question], k: int, atom_tags: dict[str, list[str]]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    rows: list[dict[str, Any]] = []
    for q in questions:
        start = time.perf_counter()
        ids = list(method(q.question, k))[:k]
        latency_ms = (time.perf_counter() - start) * 1000
        expected = set(q.expected_atom_ids)
        rank = next((i + 1 for i, atom_id in enumerate(ids) if atom_id in expected), None)
        tags_hit = any(set(atom_tags.get(atom_id, [])) & set(q.expected_tags) for atom_id in ids)
        rows.append({
            "id": q.id,
            "top": ids,
            "first_hit_rank": rank,
            "hit@1": int(rank == 1),
            "hit@k": int(rank is not None),
            "rr": 1 / rank if rank else 0.0,
            "tag_hit@k": int(tags_hit),
            "latency_ms": round(latency_ms, 2),
        })
    n = max(len(rows), 1)
    metrics = {
        "hit@1": sum(r["hit@1"] for r in rows) / n,
        f"hit@{k}": sum(r["hit@k"] for r in rows) / n,
        "mrr": sum(r["rr"] for r in rows) / n,
        f"tag_hit@{k}": sum(r["tag_hit@k"] for r in rows) / n,
        "latency_ms": sum(r["latency_ms"] for r in rows) / n,
    }
    return rows, metrics


def run(methods: list[str], k: int, *, jev_threshold: float = 0.5, questions_path: Path = QUESTIONS_PATH, kb: Any | None = None, jev_client: Any | None = None, limit: int | None = None) -> dict[str, Any]:
    from tutor import world

    kb = kb or world.open_kb()
    questions = load_questions(questions_path)
    if limit:
        questions = questions[:limit]
    atom_tags = {a["id"]: a["tags"] for a in world.list_atoms(kb)}
    results: dict[str, Any] = {"k": k, "n_questions": len(questions), "methods": {}}
    for name, method in build_methods(kb, methods, jev_threshold=jev_threshold, jev_client=jev_client).items():
        if isinstance(method, str):
            results["methods"][name] = MethodResult(name, "skipped", method).__dict__
            continue
        try:
            rows, metrics = evaluate(method, questions, k, atom_tags)
        except Exception as exc:  # Jev sin red / cuota: no tumba el benchmark
            log.warning("%s falló: %s", name, exc)
            results["methods"][name] = MethodResult(name, "skipped", f"{type(exc).__name__}: {exc}").__dict__
            continue
        results["methods"][name] = MethodResult(name, "ok", None, rows, metrics).__dict__
    return results


def table(results: dict[str, Any]) -> str:
    k = results["k"]
    header = f"{'method':<10} {'hit@1':>6} {f'hit@{k}':>6} {'MRR':>6} {f'tag@{k}':>6} {'ms':>8}  status"
    lines = [header, "-" * len(header)]
    for name, res in results["methods"].items():
        if res["status"] != "ok":
            lines.append(f"{name:<10} {'-':>6} {'-':>6} {'-':>6} {'-':>6} {'-':>8}  skipped: {res['reason']}")
            continue
        m = res["metrics"]
        lines.append(
            f"{name:<10} {m['hit@1']:>6.2f} {m[f'hit@{k}']:>6.2f} {m['mrr']:>6.3f} {m[f'tag_hit@{k}']:>6.2f} {m['latency_ms']:>8.1f}  ok"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--methods", default=",".join(ALL_METHODS), help="lista separada por comas")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("benchmarks") / "results.json")
    parser.add_argument("--jev-threshold", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=None, help="solo las primeras N preguntas")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    results = run(methods, args.k, jev_threshold=args.jev_threshold, limit=args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(table(results))
    print(f"\n{results['n_questions']} preguntas, k={args.k}; JSON en {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
