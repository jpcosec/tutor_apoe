"""CLI `kb` (spec 01 §7.3): delgado, cada comando llama a la fachada (R6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from kb.exceptions import KnowledgeBaseError, KnowledgeBaseInvalid
from kb.facade import KnowledgeBase

app = typer.Typer(help="Acceso de solo lectura a una KB sldb (spec 01).", no_args_is_help=True)

RootArg = Annotated[Path, typer.Argument(help="Raíz de la KB (donde está kb.yaml).")]
Lenient = Annotated[bool, typer.Option("--lenient", help="Abrir aunque haya errores de validación.")]


@app.command("validate")
def validate_command(root: RootArg) -> None:
    """Exit 0 si la KB es válida; 1 y una línea por error si no."""
    _open(root, lenient=False)


@app.command("retrack")
def retrack_command(
    root: RootArg,
    ref: Annotated[list[str] | None, typer.Argument()] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="No escribe: lista en `would_retrack` qué tocaría.")
    ] = False,
) -> None:
    """Re-extrae los documentos cuya huella no calza (escribe en el store, no en los `.md`)."""
    from kb.retracking import retrack

    report = retrack(root, ref, dry_run)
    typer.echo(report.model_dump_json(indent=2))
    if report.failed:
        raise typer.Exit(1)


@app.command("show")
def show_command(root: RootArg, ref: str, lenient: Lenient = False) -> None:
    """Un documento como JSON."""
    typer.echo(_open(root, lenient).get(ref).model_dump_json(indent=2))


@app.command("query")
def query_command(
    root: RootArg,
    model: Annotated[str | None, typer.Option("--model")] = None,
    tag: Annotated[str | None, typer.Option("--tag")] = None,
    family: Annotated[str | None, typer.Option("--family")] = None,
    exact: Annotated[bool, typer.Option("--exact", help="Sin subclases ni descendientes.")] = False,
    eligible: Annotated[bool, typer.Option("--eligible")] = False,
    lenient: Lenient = False,
) -> None:
    """Lista JSON ordenada de refs; exactamente un selector."""
    if sum(value is not None for value in (model, tag, family)) != 1:
        raise typer.BadParameter("usa exactamente uno de --model, --tag, --family")
    kb = _open(root, lenient)
    if model is not None:
        documents = kb.by_model(model, include_subclasses=not exact)
    elif tag is not None:
        documents = kb.by_tag(tag, include_descendants=not exact)
    else:
        documents = kb.by_family(family or "")
    typer.echo(json.dumps(sorted(d.key for d in documents if d.eligible or not eligible)))


@app.command("materialize")
def materialize_command(
    root: RootArg,
    output: Annotated[Path | None, typer.Option("-o", help="Archivo de salida; se sobrescribe.")] = None,
    lenient: Lenient = False,
) -> None:
    """La KB elegible como un solo Markdown determinista."""
    text = _open(root, lenient).materialize()
    if output is None:
        typer.echo(text, nl=False)
    else:
        output.write_text(text, encoding="utf-8")


@app.command("stats")
def stats_command(root: RootArg, lenient: Lenient = False) -> None:
    """Conteos de la KB como JSON."""
    typer.echo(_open(root, lenient).stats().model_dump_json(indent=2))


def _open(root: Path, lenient: bool) -> KnowledgeBase:
    try:
        return KnowledgeBase.open_lenient(root)[0] if lenient else KnowledgeBase.open(root)
    except KnowledgeBaseInvalid as invalid:
        for error in invalid.report.errors:
            typer.echo(error.line())
        raise typer.Exit(1) from invalid
    except KnowledgeBaseError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


def main() -> None:
    app()
