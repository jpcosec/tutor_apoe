from __future__ import annotations

import re
import unicodedata
from typing import Any
from uuid import uuid4

from .pack_loader import KnowledgePack


def _normalize(text: str) -> str:
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    return text.lower()


class MesaCompiler:
    def __init__(self, pack: KnowledgePack):
        self.pack = pack
        self.atoms = pack.atoms_data['atoms']
        self.by_id = {a['id']: a for a in self.atoms}
        rules = pack.expansion_rules
        self.aliases = rules['aliases']
        self.expansions = rules['expansions']
        self.followup_markers = set(rules['followup_markers'])
        self.scoring = rules['scoring']
        self.default_tags = pack.default_tags
        self.max_atoms = pack.max_atoms

    def compile(self, query: str, previous_turn: dict[str, Any] | None = None) -> dict[str, Any]:
        previous_mesa = (previous_turn or {}).get('mesa') or {}
        previous_items = previous_mesa.get('items', [])
        previous_ids = [i['atom_id'] for i in previous_items]
        previous_tags = list(previous_mesa.get('include_tags', []))

        normalized_query = _normalize(query)
        include_tags = self._extract_tags(query)
        is_followup = False
        if not include_tags and self._is_followup(query) and previous_tags:
            include_tags = previous_tags[:]
            is_followup = True

        for default_tag in self.default_tags:
            if default_tag not in include_tags:
                include_tags.append(default_tag)

        expanded_tags = include_tags[:]
        expansion_steps: list[str] = []
        for tag in include_tags:
            extras = self.expansions.get(tag, [])
            for extra in extras:
                if extra not in expanded_tags:
                    expanded_tags.append(extra)
            if extras:
                expansion_steps.append(f'{tag} -> {", ".join(extras)}')

        ranked = self._rank_atoms(query, include_tags, expanded_tags, previous_ids)
        selected = ranked[: self.max_atoms]

        selected_ids = [item['atom_id'] for item in selected]
        retained = [doc_id for doc_id in previous_ids if doc_id in selected_ids]
        removed = [doc_id for doc_id in previous_ids if doc_id not in selected_ids]
        added = [doc_id for doc_id in selected_ids if doc_id not in previous_ids]

        summary = []
        if include_tags:
            summary.append(f'tags activos: {", ".join(include_tags)}')
        if expansion_steps:
            summary.append(f'expansiones: {" | ".join(expansion_steps)}')
        summary.append(f'se seleccionaron {len(selected)} atoms')
        if retained:
            summary.append(f'se retuvieron {len(retained)} atoms previos')
        if removed:
            summary.append(f'se removieron {len(removed)} atoms previos')

        reasoning_log = [
            {'type': 'query', 'detail': query},
            {'type': 'normalized_query', 'detail': normalized_query},
            {'type': 'followup_reuse', 'detail': 'yes' if is_followup else 'no'},
            {'type': 'inferred_tags', 'detail': include_tags},
            {'type': 'expanded_tags', 'detail': expanded_tags},
            {'type': 'previous_atom_ids', 'detail': previous_ids},
            {'type': 'retained_atom_ids', 'detail': retained},
            {'type': 'removed_atom_ids', 'detail': removed},
            {'type': 'added_atom_ids', 'detail': added},
            {
                'type': 'candidate_scores',
                'detail': [
                    {
                        'atom_id': item['atom_id'],
                        'score': item['score'],
                        'role': item['role'],
                        'why': item['why'],
                    }
                    for item in selected
                ],
            },
        ]

        mesa = {
            'mesa_id': f'mesa-{uuid4().hex[:10]}',
            'query': query,
            'include_tags': include_tags,
            'expanded_tags': expanded_tags,
            'retained_atom_ids': retained,
            'removed_atom_ids': removed,
            'added_atom_ids': added,
            'atom_ids': selected_ids,
            'items': selected,
            'reasoning_summary': summary,
            'reasoning_log': reasoning_log,
        }

        prompt_items = []
        for item in selected:
            atom = self.by_id[item['atom_id']]
            prompt_items.append({
                'atom_id': item['atom_id'],
                'title': item['title'],
                'question': atom.get('question'),
                'answer': atom.get('answer'),
                'provenance': atom.get('provenance') or atom.get('provenance_field'),
                'tags': atom.get('tags', []),
                'path': atom.get('path', ''),
                'role': item['role'],
                'why': item['why'],
                'score': item['score'],
            })

        return {
            'mesa': mesa,
            'prompt_mesa': {
                'query': query,
                'include_tags': include_tags,
                'items': prompt_items,
            },
        }

    def _extract_tags(self, query: str) -> list[str]:
        q = _normalize(query)
        tags: list[str] = []
        for alias, mapped in self.aliases.items():
            if _normalize(alias) in q:
                for tag in mapped:
                    if tag not in tags:
                        tags.append(tag)
        return tags

    def _is_followup(self, query: str) -> bool:
        q = _normalize(query).strip()
        return any(marker in q for marker in self.followup_markers) or len(q.split()) <= 4

    def _tokenize(self, text: str) -> set[str]:
        return {t for t in re.findall(r'[a-z0-9:-]+', _normalize(text)) if len(t) >= 3}

    def _rank_atoms(self, query: str, include_tags: list[str], expanded_tags: list[str], previous_ids: list[str]) -> list[dict[str, Any]]:
        q_tokens = self._tokenize(query)
        items: list[dict[str, Any]] = []

        for atom in self.atoms:
            tags = atom.get('tags', [])
            atom_id = atom['id']
            score = 0
            why: list[str] = []
            role = 'support'

            exact_tag_hits = [t for t in include_tags if t in tags]
            expanded_hits = [t for t in expanded_tags if t in tags and t not in include_tags]
            if exact_tag_hits:
                score += int(self.scoring['exact_tag']) * len(exact_tag_hits)
                role = 'exact_match'
                why.append(f"exact_tag:{','.join(exact_tag_hits)}")
            if expanded_hits:
                score += int(self.scoring['expanded_tag']) * len(expanded_hits)
                if role != 'exact_match':
                    role = 'expanded'
                why.append(f"expanded_tag:{','.join(expanded_hits)}")

            haystack = ' '.join([
                atom_id,
                atom.get('title', ''),
                atom.get('question', ''),
                atom.get('answer', ''),
                ' '.join(tags),
            ])
            overlap = sorted(q_tokens & self._tokenize(haystack))
            if overlap:
                score += int(self.scoring['lexical_overlap']) * len(overlap)
                why.append(f"lexical_overlap:{','.join(overlap[:6])}")

            if atom_id in previous_ids:
                score += int(self.scoring['retained_from_previous'])
                if role == 'support':
                    role = 'retained'
                why.append('retained_from_previous')

            pedagogy_bonus = int(self.scoring.get('pedagogy_included_bonus', 20))
            pedagogy_penalty = int(self.scoring.get('pedagogy_excluded_penalty', -10))
            theory_bonus = int(self.scoring.get('theory_bonus', 5))

            if 'layer:pedagogy' in include_tags and 'layer:pedagogy' in tags:
                score += pedagogy_bonus
            elif 'layer:pedagogy' not in include_tags and 'layer:pedagogy' in tags:
                score += pedagogy_penalty

            if 'layer:theory' in tags:
                score += theory_bonus

            if score <= 0:
                continue

            items.append({
                'atom_id': atom_id,
                'title': atom.get('title') or atom_id,
                'tags': tags,
                'path': atom.get('path', ''),
                'why': '; '.join(why),
                'score': score,
                'role': role,
            })

        items.sort(key=lambda x: (-x['score'], x['atom_id']))
        return items
