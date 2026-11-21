#!/usr/bin/env python3
"""Convierte construcciones básicas de GeoGebra (.ggb) a escenas ManimGL.

El puente no intenta evaluar toda la semántica de GeoGebra. Conserva las
coordenadas de puntos libres y las órdenes Segment, Line y Circle que dependen
solo de objetos ya representables. El resultado es una escena Python editable.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Point:
    label: str
    x: float
    y: float


@dataclass(frozen=True)
class Command:
    kind: str
    label: str
    inputs: tuple[str, ...]


def _number(value: str | None, default: float = 0) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def read_geogebra(path: Path) -> tuple[dict[str, Point], list[Command], list[str]]:
    """Devuelve puntos, órdenes soportables y advertencias de una hoja .ggb."""
    warnings: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("geogebra.xml")
    except (zipfile.BadZipFile, KeyError) as error:
        raise ValueError("El archivo debe ser una hoja GeoGebra .ggb válida con geogebra.xml.") from error
    root = ET.fromstring(xml)
    points: dict[str, Point] = {}
    for element in root.findall(".//element[@type='point']"):
        label = element.get("label")
        coords = element.find("coords")
        if not label or coords is None:
            continue
        z = _number(coords.get("z"), 1)
        if z == 0:
            warnings.append(f"{label}: punto en el infinito omitido.")
            continue
        points[label] = Point(label, _number(coords.get("x")) / z, _number(coords.get("y")) / z)
    commands: list[Command] = []
    for command in root.findall(".//command"):
        kind = command.get("name", "")
        inputs = command.find("input")
        outputs = command.find("output")
        if kind not in {"Segment", "Line", "Circle"} or inputs is None or outputs is None:
            continue
        args = tuple(value for _, value in sorted(inputs.attrib.items()))
        label = next(iter(outputs.attrib.values()), "")
        if not label:
            continue
        commands.append(Command(kind, label, args))
    return points, commands, warnings


def identifier(label: str, used: set[str]) -> str:
    base = re.sub(r"\W|^(?=\d)", "_", label) or "object"
    result = base
    number = 2
    while result in used:
        result = f"{base}_{number}"
        number += 1
    used.add(result)
    return result


def scene_code(points: dict[str, Point], commands: list[Command], scene_name: str, title: str) -> tuple[str, list[str]]:
    """Genera una escena ManimGL y devuelve advertencias de objetos omitidos."""
    warnings: list[str] = []
    used: set[str] = set()
    names = {label: identifier(label, used) for label in points}
    lines = [
        "from manimlib import *",
        "",
        "",
        f"class {scene_name}(Scene):",
        "    def construct(self):",
        f"        title = Text({title!r}, font_size=34).to_edge(UP)",
        "        axes = Axes(x_range=(-6, 6, 1), y_range=(-4, 4, 1), width=10, height=6)",
        "        self.play(Write(title), Create(axes))",
    ]
    for label, point in points.items():
        name = names[label]
        lines.extend((
            f"        {name} = Dot(axes.c2p({point.x!r}, {point.y!r}), color=YELLOW)",
            f"        {name}_label = Text({label!r}, font_size=24).next_to({name}, UR, buff=0.08)",
            f"        self.play(FadeIn({name}), Write({name}_label))",
        ))
    for command in commands:
        mapped = [names.get(label) for label in command.inputs]
        if command.kind in {"Segment", "Line"} and len(mapped) >= 2 and all(mapped[:2]):
            draw = "Line" if command.kind == "Segment" else "Line"
            extension = "" if command.kind == "Segment" else ".set_length(12)"
            name = identifier(command.label, used)
            lines.extend((
                f"        {name} = {draw}({mapped[0]}.get_center(), {mapped[1]}.get_center(), color=BLUE){extension}",
                f"        self.play(Create({name}))",
            ))
        elif command.kind == "Circle" and len(mapped) >= 2 and all(mapped[:2]):
            name = identifier(command.label, used)
            lines.extend((
                f"        {name} = Circle(radius=get_norm({mapped[1]}.get_center() - {mapped[0]}.get_center()), color=BLUE).move_to({mapped[0]}.get_center())",
                f"        self.play(Create({name}))",
            ))
        else:
            warnings.append(f"{command.kind} {command.label}: depende de objetos no representables; omitido.")
    lines.extend(("        self.wait(1)", ""))
    return "\n".join(lines), warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Convierte GeoGebra .ggb a escena ManimGL.")
    parser.add_argument("input", type=Path, help="Hoja GeoGebra .ggb")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Archivo .py de salida")
    parser.add_argument("--scene", default="GeoGebraConstruction", help="Nombre de la clase Scene")
    parser.add_argument("--title", default="Construcción GeoGebra", help="Título de la escena")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.scene):
        parser.error("--scene debe ser un identificador Python válido.")
    points, commands, warnings = read_geogebra(args.input)
    code, conversion_warnings = scene_code(points, commands, args.scene, args.title)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(code, encoding="utf-8")
    print(f"Escena creada: {args.output}")
    print(f"Puntos: {len(points)} · órdenes GeoGebra consideradas: {len(commands)}")
    for warning in warnings + conversion_warnings:
        print(f"Advertencia: {warning}", file=sys.stderr)


if __name__ == "__main__":
    main()
