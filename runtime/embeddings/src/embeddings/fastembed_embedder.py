"""Embeddings locales con fastembed (ONNX, sin red una vez descargado el modelo)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

PROVIDER = "fastembed"


class FastEmbedEmbedder:
    """`fastembed:<modelo>`; el modelo se carga la primera vez que se embebe."""

    def __init__(self, model: str, cache_dir: str | None = None) -> None:
        self.model = model
        self.cache_dir = cache_dir
        self._engine: Any = None

    def id(self) -> str:
        return f"{PROVIDER}:{self.model}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(x) for x in vector] for vector in self._load().embed(list(texts))]

    def _load(self) -> Any:
        if self._engine is None:
            from fastembed import TextEmbedding  # pyright: ignore[reportMissingImports]

            self._engine = TextEmbedding(model_name=self.model, cache_dir=self.cache_dir)
        return self._engine
