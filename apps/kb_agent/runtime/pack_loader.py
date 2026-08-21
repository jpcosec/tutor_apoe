from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class KnowledgePack:
    pack_id: str
    base_dir: Path
    manifest: dict[str, Any]
    atoms_data: dict[str, Any]
    expansion_rules: dict[str, Any]
    prompt_policy: str
    index_path: Path
    atoms_path: Path

    @property
    def brand(self) -> dict[str, Any]:
        return self.manifest.get('brand', {})

    @property
    def default_tags(self) -> list[str]:
        return list(self.manifest.get('default_tags', []))

    @property
    def max_atoms(self) -> int:
        return int(self.manifest['max_atoms'])

    @property
    def responder(self) -> dict[str, Any]:
        return dict(self.manifest.get('responder', {}))


_REQUIRED_MANIFEST_FIELDS = ['pack_id', 'title', 'language', 'default_tags', 'max_atoms', 'responder']
_REQUIRED_RULE_KEYS = ['aliases', 'expansions', 'followup_markers', 'scoring']


def _runtime_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_pack_id() -> str:
    return os.environ.get('KB_PACK', 'apos')


def get_pack_root() -> Path:
    default = _runtime_root() / 'packs'
    return Path(os.environ.get('KB_PACK_DIR', str(default))).resolve()


def load_pack(pack_id: str | None = None, pack_root: Path | None = None) -> KnowledgePack:
    effective_pack_id = pack_id or get_pack_id()
    effective_root = (pack_root or get_pack_root()).resolve()
    pack_dir = effective_root / effective_pack_id
    if not pack_dir.is_dir():
        raise RuntimeError(f'KB pack not found: {pack_dir}')

    manifest_path = pack_dir / 'pack.json'
    atoms_path = pack_dir / 'atoms.json'
    rules_path = pack_dir / 'expansion_rules.json'
    prompt_path = pack_dir / 'prompt_policy.md'
    index_path = pack_dir / 'index.html'

    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception as exc:  # pragma: no cover - fail-fast path
        raise RuntimeError(f'Invalid pack manifest at {manifest_path}: {exc}') from exc
    for field in _REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            raise RuntimeError(f'Malformed pack manifest {manifest_path}: missing {field}')
    if manifest.get('pack_id') != pack_dir.name:
        raise RuntimeError(
            f'Pack id mismatch for {pack_dir}: pack.json pack_id={manifest.get("pack_id")!r} != folder={pack_dir.name!r}'
        )
    if not isinstance(manifest.get('default_tags'), list) or not manifest['default_tags']:
        raise RuntimeError(f'Malformed pack manifest {manifest_path}: default_tags must be a non-empty list')
    responder = manifest.get('responder', {})
    if not isinstance(responder, dict) or 'model' not in responder:
        raise RuntimeError(f'Malformed pack manifest {manifest_path}: responder.model is required')

    try:
        atoms_data = json.loads(atoms_path.read_text(encoding='utf-8'))
    except Exception as exc:  # pragma: no cover - fail-fast path
        raise RuntimeError(f'Invalid atoms inventory at {atoms_path}: {exc}') from exc
    if not isinstance(atoms_data.get('atoms'), list):
        raise RuntimeError(f'Malformed atoms inventory {atoms_path}: atoms must be a list')

    try:
        expansion_rules = json.loads(rules_path.read_text(encoding='utf-8'))
    except Exception as exc:  # pragma: no cover - fail-fast path
        raise RuntimeError(f'Invalid expansion rules at {rules_path}: {exc}') from exc
    for key in _REQUIRED_RULE_KEYS:
        if key not in expansion_rules:
            raise RuntimeError(f'Malformed expansion rules {rules_path}: missing {key}')

    try:
        prompt_policy = prompt_path.read_text(encoding='utf-8').strip()
    except Exception as exc:  # pragma: no cover - fail-fast path
        raise RuntimeError(f'Invalid prompt policy at {prompt_path}: {exc}') from exc
    if not prompt_policy:
        raise RuntimeError(f'Malformed prompt policy {prompt_path}: empty file')
    if not index_path.is_file():
        raise RuntimeError(f'Pack UI file not found: {index_path}')

    return KnowledgePack(
        pack_id=effective_pack_id,
        base_dir=pack_dir,
        manifest=manifest,
        atoms_data=atoms_data,
        expansion_rules=expansion_rules,
        prompt_policy=prompt_policy,
        index_path=index_path,
        atoms_path=atoms_path,
    )
