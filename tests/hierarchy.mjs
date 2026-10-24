import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = readFileSync(new URL('../web/hierarchy.js', import.meta.url), 'utf8');
const {hierarchy} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const branch = {id: 'branch-apos-core-structures-schema', node_type: 'branch', parent_id: 'branch-apos-core-structures', path: 'desk/atoms/branches/atom-schema.md'};
const atom = {id: 'schema', path: 'desk/atoms/apos/core-structures/schema/atom-schema.md'};
const other = {id: 'other', path: 'desk/atoms/apos/research/atom-other.md'};
for (const items of [hierarchy([atom, branch, other]), hierarchy([atom], [atom, branch, other])]) {
  const byId = new Map(items.map(item => [item.id, item]));
  assert.equal(byId.get('schema').graph_parent, branch.id);
  assert.equal(byId.get(branch.id).graph_parent, 'branch-apos-core-structures');
  assert.equal(byId.get('branch-apos-core-structures').graph_parent, 'branch-apos');
  assert.equal(byId.get('branch-apos').graph_parent, '');
}
assert.equal(hierarchy([atom], [atom, branch, other]).some(item => item.id === 'other'), false);
const explicit = {...atom, parent_id: 'other'};
assert.equal(hierarchy([explicit], [explicit, other]).find(item => item.id === 'schema').graph_parent, 'other');
console.log('PASS: folder ancestry, search context, explicit parents');
