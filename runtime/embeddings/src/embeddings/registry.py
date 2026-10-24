"""De un `embedder_id` declarado en la KB al adaptador que lo produce."""

from __future__ import annotations

import os

from embeddings.fastembed_embedder import PROVIDER as FASTEMBED
from embeddings.fastembed_embedder import FastEmbedEmbedder


class UnknownEmbedder(ValueError):
    """Ningún adaptador produce ese `embedder_id`."""


def embedder_for(embedder_id: str, cache_dir: str | None = None) -> FastEmbedEmbedder:
    provider, _, model = embedder_id.partition(":")
    if provider == FASTEMBED and model:
        return FastEmbedEmbedder(model, cache_dir=cache_dir or os.environ.get("FASTEMBED_CACHE_PATH"))
    raise UnknownEmbedder(f"sin adaptador para {embedder_id!r}")
