"""El compilador: de la declaración y la KB al artefacto de cada rol (spec 05 §6.7)."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field

from agents.declaration import AgentDecl, AgentsDeclaration
from agents.kb_tools import KB_TOOLS
from agents.providers import body_of, is_general, section, section_documents
from kb import GOVERNANCE_TAGS, KnowledgeBase

WRITER = (
    "Redactas la respuesta que se envía a la persona. Usa solo lo que dicen estas instrucciones y "
    "el contexto del turno; si algo no está ahí, no lo inventes. Nunca afirmes que hiciste una "
    "acción que el contexto no confirma.\n"
    "Si el contexto trae el resultado de una acción: con estado `ok`, responde con sus datos; si "
    "fue rechazada por datos faltantes o inválidos, pide a la persona exactamente esos datos; si "
    "falló, dilo sin culpar a la persona. Usa el texto de «Si no entiendes» solo cuando de verdad "
    "no entiendes lo que la persona pide."
)
CLAIMS = (
    "Devuelves `text` (la respuesta) y `claims`: una entrada por cada afirmación de dominio del "
    "texto (un monto, una fecha, un identificador, un estado, un plazo, una regla o un hecho del negocio). "
    "`span` es el fragmento exacto del texto y `refs` dice de dónde sale: un documento del "
    "conocimiento, que ves como `[Modelo:nombre]`, se cita `kb:Modelo:nombre`; lo que dice el "
    "resultado de una acción se cita con su `ref` (el de la acción, `tool:<nombre>`, o el de "
    "la fila de donde sale el dato). Nunca inventes una ref. Saludos, preguntas y "
    "ofrecimientos no llevan claim. Lo que no puedas citar, no lo afirmes: di que no lo tienes."
)
STEP_TARGET = (
    "- `step_target`: el id exacto de uno de los pasos permitidos desde el paso actual, si la "
    "conversación avanza; null si ninguno aplica o si se queda donde está."
)

#: La doctrina sale del esquema de salida (spec 16): es el contrato de lo que el agente devuelve.
#: `None` es un agente que responde texto libre.
DOCTRINE: dict[str | None, str] = {
    None: WRITER,
    "TurnDecision@1": (
        "Decides el turno; nunca redactas la respuesta (eso lo hace el redactor después, con el "
        "resultado real de las acciones). Si una de tus herramientas resuelve el pedido y tienes sus "
        "argumentos, dichos por la persona o presentes en el contexto, llámala antes de responder; "
        "nunca inventes ni dejes vacío un argumento. Si falta un dato, no la llames: el redactor lo "
        "pedirá. Después respondes solo con la estructura pedida.\n"
        "- `kind`: `fallback` solo si el pedido no tiene nada que ver con lo que este agente atiende; "
        "`nl` en cualquier otro caso.\n"
        f"{STEP_TARGET}\n"
        "- `reason`: por qué, en una línea concreta; queda en el rastro del turno."
    ),
    "GateVerdict@1": (
        "Revisas el borrador de respuesta antes de que se envíe; no lo reescribes. Lo comparas con "
        "cada criterio de verificación de estas instrucciones, usando el mensaje de la persona, su "
        "perfil y el resultado de las acciones del turno. Juzgas lo que el borrador dice, no lo que "
        "omite: un criterio sobre algo que el borrador no menciona se cumple.\n"
        "- `approved`: true si el borrador cumple todos los criterios; false solo con al menos una "
        "violación.\n"
        "- `violations`: una por criterio roto, con `criterion_ref` (el id que aparece junto al "
        "criterio, `GateCriterion:<id>`), `span` (el fragmento exacto del borrador que lo rompe, "
        "copiado tal cual) y `reason` (por qué, en una línea). Sin un fragmento del borrador que "
        "citar, no hay violación."
    ),
    "DraftWithEvidence@1": f"{WRITER}\n\n{CLAIMS}",
    "Respond@1": (
        f"{WRITER}\n\nEn una sola respuesta redactas y decides a qué paso sigue la conversación.\n\n"
        f"{CLAIMS}\n{STEP_TARGET}"
    ),
}


class InstructionVariant(BaseModel, frozen=True):
    ref: str = Field(description="Documento de la variante.")
    applies_when: list[str] = Field(description="Condiciones (01 §6.4); vacío = general.")
    text: str = Field(description="Texto que se agrega a las instrucciones.")


class CompiledAgent(BaseModel, frozen=True):
    role: str = Field(description="Rol.")
    instructions: str = Field(description="Doctrina + secciones estáticas de la KB.")
    instruction_variants: list[InstructionVariant] = Field(description="Variantes por segmento, por ref.")
    dynamic_fields: list[str] = Field(description="Campos que el turno debe entregar, en orden.")
    history: int | None = Field(description="N de history:N, o None.")
    on_failure: str = Field(description="open | closed.")
    projection: str = Field(description="Proyección de la KB.")
    max_tool_iterations: int = Field(description="Tope de iteraciones.")
    output_schema: str | None = Field(default=None, description="Esquema versionado de la salida, si hay.")
    kb_tools: list[str] = Field(
        default_factory=list[str], description="Tools de lectura de su porción de la KB."
    )
    business_tools: list[str] | None = Field(
        default=None, description="Tools de negocio declaradas; None = las de siempre (F2)."
    )
    static_refs: list[str] = Field(
        default_factory=list[str],
        description="Documentos que ya van en sus secciones fijas: no se rutean (14 §6.3).",
    )
    policies: list[str] = Field(default_factory=list[str], description="Políticas (05 §6.5), en orden.")
    source_sha256: str = Field(description="Hash canónico de lo compilado (I7).")


def compile_agent(decl: AgentDecl, kb: KnowledgeBase) -> CompiledAgent:
    if decl.output_schema not in DOCTRINE:
        raise ValueError(f"{decl.role}: esquema desconocido {decl.output_schema}; los hay: {list(DOCTRINE)}")
    _check_governance(decl, kb)
    _check_policies(decl)
    framing = [f"## {FRAMING_TITLE}\n\n{decl.framing.strip()}"] if decl.framing.strip() else []
    static = [s for s in (section(kb, spec, decl.role, decl.projection) for spec in decl.context.static) if s]
    doctrine = [DOCTRINE[decl.output_schema], *([KB_TOOLS_DOCTRINE] if decl.tools else [])]
    instructions = "\n\n---\n\n".join([*doctrine, *framing, *static])
    variants = _variants(kb, decl)
    dynamic = [f for f in decl.context.dynamic if not f.startswith("history")]
    body = {
        "decl": decl.model_dump(mode="json"),
        "instructions": instructions,
        "variants": [v.model_dump() for v in variants],
    }
    return CompiledAgent(
        role=decl.role,
        instructions=instructions,
        instruction_variants=variants,
        dynamic_fields=dynamic,
        history=_history(decl),
        on_failure=decl.on_failure,
        projection=decl.projection,
        max_tool_iterations=decl.max_tool_iterations,
        policies=list(decl.policies),
        output_schema=decl.output_schema,
        static_refs=_static_refs(kb, decl, variants),
        kb_tools=_kb_tools(decl),
        business_tools=list(decl.business_tools) if decl.business_tools is not None else None,
        source_sha256=hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
    )


def compile_all(declaration: AgentsDeclaration, kb: KnowledgeBase) -> dict[str, CompiledAgent]:
    return {decl.role: compile_agent(decl, kb) for decl in declaration.agents}


FRAMING_TITLE = "Tu tarea"


#: Los campos dinámicos que llevan conocimiento (05 §6.5, `deny_if_no_context`).
KNOWLEDGE_FIELDS = frozenset(
    {"bundle", "grounding", "tool_result", "profile", "summaries", "open_events", "records"}
)


def _check_policies(decl: AgentDecl) -> None:
    """Cada política compila solo donde tiene sentido (05 §6.5)."""
    fields = {f.split(":")[0] for f in decl.context.dynamic}
    if "deny_if_no_context" in decl.policies and not (fields & (KNOWLEDGE_FIELDS | {"history"})):
        raise ValueError(f"{decl.role}: deny_if_no_context necesita al menos un campo de conocimiento")


class GovernanceVisible(ValueError):
    """Un agente del runtime vería los documentos que lo gobiernan (spec 16 §5)."""


def _check_governance(decl: AgentDecl, kb: KnowledgeBase) -> None:
    """Ni su proyección ni sus secciones fijas pueden nombrar `ProjectionDoc`, `AgentDoc` o `PipelineDoc`."""
    governing = kb.governing_models()
    projected = sorted(set(kb.projection(decl.projection).models) & set(governing))
    governing_tags = {
        t for m in kb.models if m.name in governing for t in m.semantic_tags if t.startswith("type.")
    }
    tags = sorted(s.tag for s in decl.context.static if s.tag in governing_tags | set(GOVERNANCE_TAGS))
    if projected or tags:
        raise GovernanceVisible(f"{decl.role}: su proyección o sus secciones ven {projected or tags}")


KB_TOOLS_DOCTRINE = (
    "Si para responder te falta conocimiento que no está en el contexto, búscalo en tu porción de la "
    "KB con kb_explore_multi y léelo con kb_show antes de afirmarlo. Solo ves tu porción."
)


def _kb_tools(decl: AgentDecl) -> list[str]:
    unknown = sorted(set(decl.tools) - set(KB_TOOLS))
    if unknown:
        raise ValueError(f"{decl.role}: tools de KB desconocidas {unknown}; las hay: {list(KB_TOOLS)}")
    return list(decl.tools)


def _static_refs(kb: KnowledgeBase, decl: AgentDecl, variants: list[InstructionVariant]) -> list[str]:
    """Lo que el agente ya lee en sus instrucciones: rutearlo de nuevo sería ruido duplicado."""
    rendered = {
        d.key
        for spec in decl.context.static
        if spec.render != "framing"
        for d in section_documents(kb, spec, decl.role, decl.projection)
    }
    return sorted(rendered | {v.ref for v in variants})


def _variants(kb: KnowledgeBase, decl: AgentDecl) -> list[InstructionVariant]:
    documents = {
        d.key: d
        for spec in decl.context.static
        if spec.render == "documents"
        for d in section_documents(kb, spec, decl.role, decl.projection)
        if not is_general(d)
    }.values()
    return [
        InstructionVariant(
            ref=d.key,
            applies_when=[str(c) for c in d.payload.get("applies_when") or []],  # pyright: ignore[reportGeneralTypeIssues, reportUnknownVariableType, reportUnknownArgumentType]
            text=body_of(kb, d),
        )
        for d in sorted(documents, key=lambda d: d.key)
    ]


def _history(decl: AgentDecl) -> int | None:
    for field in decl.context.dynamic:
        if field.startswith("history:") and field.removeprefix("history:").isdigit():
            return int(field.removeprefix("history:"))
    return None
