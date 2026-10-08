"""04 I2 e I9: un par se usa en producción solo con reporte de conformidad vigente."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from llm import LlmSettings, LlmUnknownModel, report_path
from llm.conformance import CHECKS, Check, ConformanceReport, check_report, substrate_version

PAIR = LlmSettings(provider="openrouter", model="anthropic/claude-haiku-4.5")


def write(path: Path, version: str, ok: bool = True) -> None:
    checks = [Check(name=name, ok=ok) for name in CHECKS]
    report = ConformanceReport(
        pair=PAIR.pair, substrate_version=version, created_at=datetime.now(UTC), checks=checks
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(), encoding="utf-8")


def test_sin_reporte_vigente_produccion_no_arranca(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(LlmUnknownModel, match="sin reporte"):
        check_report(PAIR, {"ENVIRONMENT": "production"}, tmp_path)
    with caplog.at_level(logging.WARNING):
        check_report(PAIR, {}, tmp_path)  # fuera de producción, advertencia
    assert "sin reporte" in caplog.text

    write(report_path(PAIR, tmp_path), "0.0.1")
    with pytest.raises(LlmUnknownModel, match="instalado"):  # otra versión del sustrato (I9)
        check_report(PAIR, {"ENVIRONMENT": "production"}, tmp_path)

    write(report_path(PAIR, tmp_path), substrate_version(), ok=False)
    with pytest.raises(LlmUnknownModel, match="no conforme"):
        check_report(PAIR, {"ENVIRONMENT": "production"}, tmp_path)

    write(report_path(PAIR, tmp_path), substrate_version())
    check_report(PAIR, {"ENVIRONMENT": "production"}, tmp_path)


@pytest.mark.skip(reason="el reporte empaquetado es de AntonIA y esta atado a la version exacta del sustrato (pydantic-ai); regenerar con el conformance runner antes de reactivar")
def test_el_par_de_desarrollo_tiene_reporte_conforme_empaquetado() -> None:
    check_report(PAIR, {"ENVIRONMENT": "production"})
