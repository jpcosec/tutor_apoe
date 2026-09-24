import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Background, Controls, Handle, MiniMap, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesInitialized, useNodesState, useReactFlow} from '@xyflow/react';
import htm from 'htm';
import dagre from 'dagre';

const html = htm.bind(React.createElement);
const COLORS = ['#4fc3d9', '#e6a85c', '#7cba7c', '#c97db9', '#9b7fd4', '#ff6b6b'];

function hierarchy(atom) {
  const pieces = atom.path.split('/');
  const apos = pieces.indexOf('apos');
  return apos >= 0 ? ['apos', ...pieces.slice(apos + 1, -1)] : ['fuentes', ...pieces.slice(3, -1)];
}

function colour(name) {
  let total = 0;
  for (const letter of name) total += letter.charCodeAt(0);
  return COLORS[total % COLORS.length];
}

function Node({data, selected}) {
  const root = data.kind === 'root';
  const branch = data.kind === 'branch';
  return html`<div className=${`node ${root ? 'node-root' : ''} ${branch ? 'node-branch' : ''} ${selected ? 'selected' : ''}`}
      style=${{ '--node-colour': data.colour }}>
    <${Handle} type="target" position=${Position.Left}/>
    <div className="node-kicker">${root ? 'BASE DE CONOCIMIENTO' : branch ? 'CATEGORÍA' : data.node_type || data.question || 'átomo'}</div>
    <div className="node-title">${data.label}</div>
    <${Handle} type="source" position=${Position.Right}/>
  </div>`;
}
const nodeTypes = {knowledge: Node};

function buildGraph(atoms, direction, showAtoms) {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({rankdir: direction, ranksep: 72, nodesep: 18, marginx: 40, marginy: 40});
  const nodes = [{id: 'root', type: 'knowledge', data: {kind: 'root', label: 'Teoría APOS', colour: '#d4a574'}, position: {x: 0, y: 0}}];
  const edges = [];
  graph.setNode('root', {width: 150, height: 48});
  const branches = new Map([['', 'root']]);
  const ids = new Set(atoms.map(atom => atom.id));
  atoms.forEach(atom => {
    let parent = 'root'; let key = '';
    hierarchy(atom).forEach((part, level) => {
      if (!showAtoms && level > 1) return;
      key += `/${part}`;
      if (!branches.has(key)) {
        const id = `branch:${key}`; const tone = colour(hierarchy(atom)[0]);
        branches.set(key, id);
        nodes.push({id, type: 'knowledge', data: {kind: 'branch', label: part.replaceAll('-', ' '), colour: tone}, position: {x: 0, y: 0}});
        edges.push({id: `${parent}-${id}`, source: parent, target: id, style: {stroke: tone, strokeWidth: level === 0 ? 2 : 1.3}});
        graph.setNode(id, {width: 116, height: 40}); graph.setEdge(parent, id);
      }
      parent = branches.get(key);
    });
    if (showAtoms) {
      const id = `atom:${atom.id}`; const tone = colour(hierarchy(atom)[0]);
      nodes.push({id, type: 'knowledge', data: {...atom, kind: 'atom', label: atom.title, colour: tone}, position: {x: 0, y: 0}});
      const actualParent = atom.parent_id && ids.has(atom.parent_id) ? `atom:${atom.parent_id}` : parent;
      edges.push({id: `${actualParent}-${id}`, source: actualParent, target: id, style: {stroke: `${tone}99`, strokeWidth: 1}});
      graph.setNode(id, {width: 165, height: 42}); graph.setEdge(actualParent, id);
    }
  });
  dagre.layout(graph);
  return {
    nodes: nodes.map(node => {
      const pos = graph.node(node.id);
      const width = node.data.kind === 'atom' ? 165 : node.data.kind === 'root' ? 150 : 116;
      return {...node, position: {x: pos.x - width / 2, y: pos.y - 21}};
    }), edges,
  };
}

function App() {
  const [atoms, setAtoms] = useState([]);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [term, setTerm] = useState('');
  const [direction, setDirection] = useState('TB');
  const [showAtoms, setShowAtoms] = useState(false);
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState(null);
  const [status, setStatus] = useState('Cargando la base de conocimiento…');
  const {fitView} = useReactFlow();
  const nodesReady = useNodesInitialized();

  const draw = useCallback((items, layout, leaves) => {
    const next = buildGraph(items, layout, leaves);
    setNodes(next.nodes); setEdges(next.edges);
    setTimeout(() => fitView({padding: .14, duration: 300}), 350);
  }, [fitView, setEdges, setNodes]);

  const search = useCallback(async (value = '') => {
    setStatus('Consultando SLDB…');
    const response = await fetch(`/api/search?q=${encodeURIComponent(value)}`);
    const data = await response.json();
    if (!response.ok) { setStatus(data.detail || 'No se pudo consultar SLDB.'); return; }
    const leaves = Boolean(value) || showAtoms;
    if (value) setShowAtoms(true);
    setAtoms(data.atoms); setSelected(null); setDraft(null); draw(data.atoms, direction, leaves);
    setStatus(`${data.atoms.length} átomos · ${value ? `resultado para “${value}”` : 'vista completa'}`);
  }, [direction, draw, showAtoms]);

  useEffect(() => { search(); }, []);
  useEffect(() => { if (atoms.length) draw(atoms, direction, showAtoms); }, [direction, showAtoms]);
  useEffect(() => { if (nodesReady) fitView({padding: .14, duration: 250}); }, [nodesReady, nodes, fitView]);
  const topics = useMemo(() => [...new Set(atoms.flatMap(atom => atom.tags.filter(tag => tag.startsWith('topic:'))))].sort(), [atoms]);
  const select = atom => { setSelected(atom); setDraft({...atom, tags: [...atom.tags]}); };
  const onNodeClick = (_, node) => { if (node.data.kind === 'atom') select(node.data); };
  const save = async event => {
    event.preventDefault();
    if (!draft) return;
    setStatus('Guardando y reindexando SLDB…');
    const response = await fetch(`/api/atoms/${encodeURIComponent(draft.id)}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...draft, tags: draft.tags})});
    const data = await response.json();
    if (!response.ok) { setStatus(data.detail || 'No se pudo guardar el átomo.'); return; }
    const updated = data.atom; const next = atoms.map(atom => atom.id === updated.id ? updated : atom);
    setAtoms(next); select(updated); draw(next, direction, showAtoms); setStatus(`Guardado: ${updated.title}`);
  };
  const addChild = async () => {
    if (!selected) return;
    const title = window.prompt('Título del nuevo hijo:');
    if (!title) return;
    const node_type = window.prompt('Tipo de nodo (por ejemplo: knowledge, branch, example):', 'knowledge') || 'knowledge';
    setStatus('Creando hijo y reindexando SLDB…');
    const response = await fetch(`/api/atoms/${encodeURIComponent(selected.id)}/children`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title, node_type})});
    const data = await response.json();
    if (!response.ok) { setStatus(data.detail || 'No se pudo crear el hijo.'); return; }
    const next = [...atoms, data.atom]; setAtoms(next); setShowAtoms(true); select(data.atom); draw(next, direction, true); setStatus(`Hijo creado: ${data.atom.title}`);
  };

  return html`<main className="shell">
    <header><div><p className="eyebrow">VISOR DE CONOCIMIENTO · SLDB</p><h1>Tutor APOE</h1><p className="subtitle">Teoría APOS, sin chatbot ni modelo generativo.</p></div>
      <div className="help">${status}<br/><span>Selecciona un átomo para editar su fuente Markdown.</span></div></header>
    <section className="toolbar"><form onSubmit=${event => {event.preventDefault(); search(term)}}><input value=${term} onInput=${event => setTerm(event.target.value)} placeholder="Buscar texto o tag: topic:schema"/><button>Buscar</button><button type="button" className="secondary" onClick=${() => {setTerm(''); search('')}}>Limpiar</button></form>
      <div className="layouts"><button className=${direction === 'TB' ? 'active' : ''} onClick=${() => setDirection('TB')}>Ancho</button><button className=${direction === 'LR' ? 'active' : ''} onClick=${() => setDirection('LR')}>Alto</button><button className=${showAtoms ? 'active' : ''} onClick=${() => setShowAtoms(!showAtoms)}>${showAtoms ? 'Ocultar átomos' : 'Ver átomos'}</button></div></section>
    <section className="topics"><span>Temas visibles</span>${topics.slice(0, 14).map(tag => html`<button key=${tag} onClick=${() => {setTerm(tag); search(tag)}}>${tag.replace('topic:', '')}</button>`)}</section>
    <section className="workspace"><div className="canvas"><${ReactFlow} nodes=${nodes} edges=${edges} nodeTypes=${nodeTypes} onNodesChange=${onNodesChange} onEdgesChange=${onEdgesChange} onNodeClick=${onNodeClick} onPaneClick=${() => {}} fitView proOptions=${{hideAttribution: true}} minZoom=${.08} maxZoom=${1.8}><${Background} gap=${24} color="rgba(212,165,116,.14)"/><${Controls}/><${MiniMap} nodeColor=${node => node.data.colour} maskColor="rgba(7, 11, 18, .75)"/></${ReactFlow}></div></section>
    ${selected && draft && html`<div className="modal-backdrop" onClick=${() => {setSelected(null); setDraft(null)}}><aside className="detail modal" onClick=${event => event.stopPropagation()}><button className="modal-close" type="button" onClick=${() => {setSelected(null); setDraft(null)}} aria-label="Cerrar editor">×</button><p className="eyebrow">EDITAR ÁTOMO</p><form className="editor" onSubmit=${save}><label>Título<input value=${draft.title} onInput=${e => setDraft({...draft, title: e.target.value})}/></label><label>Tipo de nodo <small>texto libre</small><input value=${draft.node_type} onInput=${e => setDraft({...draft, node_type: e.target.value})}/></label><label>Átomo padre <small>vacío = jerarquía de carpetas</small><input value=${draft.parent_id} onInput=${e => setDraft({...draft, parent_id: e.target.value})}/></label><label>Pregunta<select value=${draft.question} onChange=${e => setDraft({...draft, question: e.target.value})}>${['what','why','how','how_not','when','where','for_whom'].map(option => html`<option key=${option}>${option}</option>`)}</select></label><label>Tags <small>separados por coma</small><input value=${draft.tags.join(', ')} onInput=${e => setDraft({...draft, tags: e.target.value.split(',').map(tag => tag.trim()).filter(Boolean)})}/></label><label>Respuesta<textarea rows="7" value=${draft.answer} onInput=${e => setDraft({...draft, answer: e.target.value})}/></label><label>Procedencia<textarea rows="5" value=${draft.provenance} onInput=${e => setDraft({...draft, provenance: e.target.value})}/></label><div className="modal-actions"><button>Guardar átomo</button><button type="button" className="secondary" onClick=${addChild}>Add child</button></div><footer>${selected.path}</footer></form></aside></div>`}
  </main>`;
}
createRoot(document.getElementById('root')).render(html`<${ReactFlowProvider}><${App}/></${ReactFlowProvider}>`);
