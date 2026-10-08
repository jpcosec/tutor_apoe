"""Ajustes de un par proveedor|modelo (spec 04 §7)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LlmSettings(BaseModel, frozen=True):
    provider: str = Field(description="Proveedor de Pydantic AI: openrouter, bedrock, openai, test…")
    model: str = Field(description="Modelo del proveedor.")
    timeout_seconds: float = Field(default=30.0, description="Plazo por petición.")
    max_attempts: int = Field(default=2, description="Reintentos del transporte.")
    max_output_tokens: int | None = Field(default=None, description="Tope de tokens de salida.")
    temperature: float | None = Field(default=None, description="Temperatura; None = la del proveedor.")
    base_url: str | None = Field(default=None, description="Para proveedores OpenAI-compatibles.")
    region: str | None = Field(default=None, description="Para Bedrock.")
    log_prompts: bool = Field(default=False, description="Registrar prompts (nunca en producción).")
    fallback: LlmSettings | None = Field(
        default=None,
        description="Par de respaldo si el primero falla (`FallbackModel`); None = sin respaldo.",
    )

    @property
    def pair(self) -> str:
        return f"{self.provider}|{self.model}"
