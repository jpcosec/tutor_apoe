"""Adaptadores de embeddings (decisión E1–E5 de decisiones-librerias-y-reglas.md).

Cada adaptador cumple el puerto `Embedder` de sldb (`id() -> str`,
`embed(texts) -> list[list[float]]`) y su `id()` es el que la KB declara en
`kb.index.embedder_id`, con la forma `<proveedor>:<modelo>`. El módulo 01 nunca
importa este paquete: lo recibe inyectado por el ensamblaje (10).
"""

from embeddings.fastembed_embedder import FastEmbedEmbedder
from embeddings.registry import UnknownEmbedder, embedder_for

__all__ = ["FastEmbedEmbedder", "UnknownEmbedder", "embedder_for"]
