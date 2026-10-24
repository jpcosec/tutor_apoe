"""CLI `tutor` (entry point `tutor = "tutor.cli:main"`; mientras tanto `python -m tutor.cli`).

    tutor kb build [--atoms desk/atoms] [--out kbs/apos] [--embedder hash]
    tutor kb validate --kb kbs/apos
    tutor kb rank --kb kbs/apos "qué es la encapsulación en APOS" --k 5
    tutor kb show --kb kbs/apos ATOM_ID
    tutor ask --kb kbs/apos --model test "¿Qué diferencia una acción de un proceso?" [--json]
    tutor chat --kb kbs/apos --model google-gla:gemini-2.5-flash

Sin red con `TUTOR_EMBEDDER=hash` y `--model test`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any

import typer

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

app = typer.Typer(help="Tutor APOS sobre una KB sldb.", no_args_is_help=True)
kb_app = typer.Typer(help="Construir, validar y consultar la KB.", no_args_is_help=True)
app.add_typer(kb_app, name="kb")

KbOpt = Annotated[Path | None, typer.Option("--kb", help="Raíz de la KB (kb.yaml); por defecto TUTOR_KB o kbs/apos.")]
ModelOpt = Annotated[
    str,
    typer.Option(
        "--model",
        help="test | provider:model (openrouter:deepseek/deepseek-v4.1-flash, openai:gpt-4o-mini…). Por defecto TUTOR_MODEL o test.",
    ),
]
#: Se lee al importar: con direnv, `.env.defaults` del proyecto ya está en el entorno.
DEFAULT_MODEL = os.environ.get("TUTOR_MODEL", "test")
RoleOpt = Annotated[str, typer.Option("--role", help="Rol del AgentDoc.")]


@kb_app.command("build")
def kb_build(
    atoms: Annotated[Path, typer.Option("--atoms", help="Carpeta con los átomos fuente.")] = Path("desk/atoms"),
    out: Annotated[Path, typer.Option("--out", help="Raíz de la KB a generar.")] = Path("kbs/apos"),
    embedder: Annotated[str | None, typer.Option("--embedder", help="hash | fastembed[:modelo].")] = None,
    pack: Annotated[Path, typer.Option("--pack", help="Carpeta con persona.md y prompt_policy.md.")] = Path(
        "apps/kb_agent/packs/apos"
    ),
    no_index: Annotated[bool, typer.Option("--no-index", help="No refrescar el índice de embeddings.")] = False,
) -> None:
    """Genera la KB desde los átomos (`tutor.kb_build`); exit 1 si no valida."""
    from tutor.kb_build import build

    report = build(atoms, out, pack_dir=pack if pack.is_dir() else None, embedder_name=embedder, index=not no_index)
    if not report.is_valid:
        for error in report.errors:
            typer.echo(error.line(), err=True)
        typer.echo(f"KB inválida: {len(report.errors)} errores", err=True)
        raise typer.Exit(1)
    typer.echo(f"KB válida en {out}")


@kb_app.command("validate")
def kb_validate(kb: KbOpt = None) -> None:
    """Abre y valida la KB con `kb`; exit 1 y una línea por error si no es válida."""
    from kb import KnowledgeBaseError, KnowledgeBaseInvalid

    from tutor import world

    try:
        opened = world.open_kb(kb, build_if_missing=False)
    except KnowledgeBaseInvalid as invalid:
        for error in invalid.report.errors:
            typer.echo(error.line(), err=True)
        typer.echo(f"KB inválida: {len(invalid.report.errors)} errores", err=True)
        raise typer.Exit(1) from invalid
    except KnowledgeBaseError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    report = opened.validate()
    if not report.is_valid:
        for error in report.errors:
            typer.echo(error.line(), err=True)
        raise typer.Exit(1)
    stats = opened.stats()
    typer.echo(f"KB válida: {opened.name} ({stats.documents} documentos, {stats.eligible} elegibles)")


@kb_app.command("rank")
def kb_rank(
    query: Annotated[str, typer.Argument(help="Pregunta o texto a comparar.")],
    kb: KbOpt = None,
    k: Annotated[int, typer.Option("--k", help="Cuántos átomos.")] = 5,
) -> None:
    """Los `k` átomos más parecidos: tabla id / score / title."""
    from tutor import world

    opened = world.open_kb(kb)
    hits = world.rank(opened, query, k)
    if not hits:
        typer.echo("sin resultados")
        return
    width = max(len(atom_id) for atom_id, _ in hits)
    typer.echo(f"{'id'.ljust(width)}  score  title")
    for atom_id, score in hits:
        atom = world.get_atom(opened, atom_id) or {}
        typer.echo(f"{atom_id.ljust(width)}  {score:.3f}  {atom.get('title', '')}")


@kb_app.command("show")
def kb_show(atom_id: Annotated[str, typer.Argument(help="Id del átomo o rama.")], kb: KbOpt = None) -> None:
    """Un átomo o rama como JSON (vista plana de `tutor.world`)."""
    from tutor import world

    atom = world.get_atom(world.open_kb(kb), atom_id)
    if atom is None:
        typer.echo(f"no existe: {atom_id}", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(atom, ensure_ascii=False, indent=2))


@app.command("ask")
def ask(
    question: Annotated[str, typer.Argument(help="La pregunta.")],
    kb: KbOpt = None,
    model: ModelOpt = DEFAULT_MODEL,
    role: RoleOpt = "tutor",
    k: Annotated[int, typer.Option("--k", help="Tamaño de la mesa.")] = 8,
    as_json: Annotated[bool, typer.Option("--json", help="Volcar el TurnResult como JSON.")] = False,
) -> None:
    """Un turno del tutor: imprime la respuesta y después la mesa (átomos con score/why)."""
    from tutor import world
    from tutor.agent import answer

    turn = answer(question, kb=world.open_kb(kb), model=model, role=role, k=k)
    if as_json:
        typer.echo(json.dumps(turn.to_dict(), ensure_ascii=False, indent=2))
        return
    typer.echo(turn.reply)
    typer.echo("")
    typer.echo(render_mesa_text(turn.mesa))


@app.command("chat")
def chat(kb: KbOpt = None, model: ModelOpt = DEFAULT_MODEL, role: RoleOpt = "tutor", show_mesa: Annotated[bool, typer.Option("--mesa/--no-mesa", help="Mostrar la mesa tras cada respuesta.")] = True) -> None:
    """REPL multi-turno en memoria; `exit`, `quit` o Ctrl-D para salir."""
    from tutor import world
    from tutor.agent import Conversation

    conversation = Conversation(kb=world.open_kb(kb), model=model, role=role)
    typer.echo(f"tutor APOS · modelo {model} · escribe `exit` para salir")
    while True:
        try:
            question = input("tú> ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit", "salir"}:
            break
        turn = conversation.ask(question)
        typer.echo(f"tutor> {turn.reply}")
        if show_mesa:
            typer.echo(render_mesa_text(turn.mesa, indent="  "))
        typer.echo("")


@app.command("web")
def web(
    kb: KbOpt = None,
    model: ModelOpt = DEFAULT_MODEL,
    role: RoleOpt = "tutor",
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8300,
) -> None:
    """Sirve la UI web del tutor (`tutor.web`) con uvicorn."""
    import uvicorn

    from tutor.web import create_app

    uvicorn.run(create_app(kb, model=model, role=role), host=host, port=port)


def render_mesa_text(mesa: dict[str, Any], indent: str = "") -> str:
    lines = [f"{indent}mesa · turno {mesa.get('turn', 1)} · {len(mesa.get('items', []))} átomos"]
    for item in mesa.get("items", []):
        lines.append(f"{indent}  {item['score']:.3f}  {item['role']:<9} {item['atom_id']}  ({item['why']})")
    for note in mesa.get("reasoning_summary", []):
        lines.append(f"{indent}  · {note}")
    if mesa.get("reads"):
        lines.append(f"{indent}  · leídos con show_atom: {', '.join(mesa['reads'])}")
    return "\n".join(lines)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
