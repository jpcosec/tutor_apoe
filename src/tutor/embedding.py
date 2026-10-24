"""Embedders para la KB del tutor.

`kb.KnowledgeBase.open(root, embedder)` recibe un objeto con el puerto `Embedder` de sldb
(`id() -> str`, `embed(texts) -> list[list[float]]`) y exige que `id()` coincida con
`kb.index.embedder_id` de `kb.yaml`.

- `HashEmbedder`: determinista, sin red ni modelos: hashing de n-gramas de caracteres (y
  palabras) a un vector denso de 256 dimensiones, normalizado. Es el embedder por defecto y
  el que la KB generada declara, para que las pruebas corran aisladas (Docker).
- `get_embedder(name)`: `hash` (o `hash:<id>`) → `HashEmbedder`; `fastembed` o
  `fastembed:<modelo>` → el adaptador de `embeddings` si fastembed está instalado, si no
  cae a `HashEmbedder`. Sin nombre, manda `TUTOR_EMBEDDER`; sin la variable, `hash`.
"""

from __future__ import annotations

import logging
import math
import os
import re
import unicodedata
import zlib
from collections.abc import Sequence

log = logging.getLogger(__name__)

HASH_DIM = 256
HASH_PROVIDER = "hash"
HASH_VARIANT = f"char-ngram-{HASH_DIM}"
HASH_ID = f"{HASH_PROVIDER}:{HASH_VARIANT}"
DEFAULT_FASTEMBED_MODEL = "jinaai/jina-embeddings-v2-base-es"
ENV_VAR = "TUTOR_EMBEDDER"

_WORD = re.compile(r"[a-z0-9]+")


class HashEmbedder:
    """Vector denso de `dim` dimensiones por hashing de n-gramas de caracteres (3–5) y palabras.

    Determinista entre procesos (usa crc32, no `hash()`), sin dependencias ni red. Texto
    normalizado: minúsculas y sin acentos, para que «encapsulación» y «encapsulacion» coincidan.
    """

    def __init__(self, dim: int = HASH_DIM, ngrams: tuple[int, ...] = (3, 4, 5)) -> None:
        self.dim = dim
        self.ngrams = ngrams

    def id(self) -> str:
        return HASH_ID if self.dim == HASH_DIM else f"{HASH_PROVIDER}:char-ngram-{self.dim}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        counts: dict[str, int] = {}
        for feature in self._features(text):
            counts[feature] = counts.get(feature, 0) + 1
        vector = [0.0] * self.dim
        for feature, count in counts.items():
            digest = zlib.crc32(feature.encode("utf-8"))
            index = digest % self.dim
            sign = 1.0 if (digest >> 31) & 1 else -1.0
            vector[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(x * x for x in vector))
        return [x / norm for x in vector] if norm else vector

    def _features(self, text: str) -> list[str]:
        words = _WORD.findall(normalize(text))
        features = [f"w:{w}" for w in words]
        for word in words:
            padded = f" {word} "
            for n in self.ngrams:
                features.extend(f"c{n}:{padded[i : i + n]}" for i in range(max(len(padded) - n + 1, 0)))
        return features


def normalize(text: str) -> str:
    """Minúsculas y sin diacríticos (NFKD, descartando marcas combinantes)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def get_embedder(name: str | None = None):
    """El embedder pedido por nombre (`hash`, `hash:<id>`, `fastembed`, `fastembed:<modelo>`).

    Sin `name`, lee `TUTOR_EMBEDDER`; sin la variable, `HashEmbedder`. Si se pide fastembed y
    no está instalado, avisa y devuelve `HashEmbedder` (sin red no hay otra opción).
    """
    chosen = (name or os.environ.get(ENV_VAR) or HASH_PROVIDER).strip()
    provider, _, model = chosen.partition(":")
    if provider == HASH_PROVIDER:
        match = re.fullmatch(r"char-ngram-(\d+)", model) if model else None
        return HashEmbedder(int(match.group(1))) if match else HashEmbedder()
    if provider == "fastembed":
        try:
            import fastembed  # noqa: F401  # pyright: ignore[reportMissingImports]
            from embeddings import embedder_for
        except ImportError:
            log.warning("fastembed no está instalado; se usa %s", HASH_ID)
            return HashEmbedder()
        return embedder_for(f"fastembed:{model or DEFAULT_FASTEMBED_MODEL}")
    raise ValueError(f"embedder desconocido: {chosen!r} (usa hash, fastembed o fastembed:<modelo>)")


__all__ = ["HASH_ID", "HashEmbedder", "get_embedder", "normalize"]
