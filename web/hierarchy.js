// Complete folder ancestry without changing the source atoms or their parent_id.
export function hierarchy(atoms, context = atoms) {
  const all = new Map(context.map(atom => [atom.id, atom]));
  const parents = new Map();
  const folder = path => {
    if (!path) return '';
    const id = `branch-${path.replaceAll('/', '-')}`;
    if (!all.has(id)) {
      all.set(id, {id, title: path.split('/').at(-1), node_type: 'branch',
        kind: 'folder', tags: [], path: `desk/atoms/${path}`});
    }
    parents.set(id, folder(path.split('/').slice(0, -1).join('/')));
    return id;
  };
  for (const atom of context) {
    const relative = atom.path.replace(/^desk\/atoms\//, '');
    if (!relative.startsWith('branches/')) {
      const directory = relative.split('/').slice(0, -1).join('/');
      const inferred = folder(directory);
      parents.set(atom.id, atom.parent_id || inferred);
    }
  }
  for (const atom of context) {
    if (atom.parent_id) parents.set(atom.id, atom.parent_id);
  }
  const result = new Map();
  const include = (id, visiting = new Set()) => {
    if (result.has(id) || !all.has(id) || visiting.has(id)) return;
    visiting.add(id);
    const atom = all.get(id);
    const parent = parents.get(id) || '';
    include(parent, visiting);
    result.set(id, {...atom, graph_parent: result.has(parent) ? parent : ''});
  };
  atoms.forEach(atom => include(atom.id));
  return [...result.values()];
}
