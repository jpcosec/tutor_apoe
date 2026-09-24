import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Background, Controls, Handle, MiniMap, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState, useReactFlow} from '@xyflow/react';
import htm from 'htm';
import dagre from 'dagre';

const html = htm.bind(React.createElement);
const COLORS = ['#4fc3d9', '#e6a85c', '#7cba7c', '#c97db9', '#9b7fd4', '#ff6b6b'];

function family(atom) {
  const pieces = atom.path.split('/');
  const apos = pieces.indexOf('apos');
  return apos >= 0 ? (pieces[apos + 1] || 'fuentes') : 'fuentes';
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
    <div className="node-kicker">${root ? 'BASE DE CONOCIMIENTO' : branch ? 'TEMA' : data.question || 'átomo'}</div>
    <div className="node-title">${data.label}</div>
    ${!root && !branch && html`<div className="node-tags">${data.tags.slice(0, 3).map(tag => html`<span key=${tag}>${tag}</span>`)}</div>`}
    <${Handle} type="source" position=${Position.Right}/>
  </div>`;
}
const nodeTypes = {knowledge: Node};

function buildGraph(atoms, direction) {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({rankdir: direction, ranksep: 100, nodesep: 28, marginx: 40, marginy: 40});
  const nodes = [{id: 'root', type: 'knowledge', data: {kind: 'root', label: 'Teoría APOS', colour: '#d4a574'}, position: {x: 0, y: 0}}];
  const edges = [];
  graph.setNode('root', {width: 190, height: 64});
  const byFamily = new Map();
  atoms.forEach(atom => {
    const key = family(atom);
    byFamily.set(key, [...(byFamily.get(key) || []), atom]);
  });
  [...byFamily.entries()].sort().forEach(([name, members]) => {
    const branchId = `family:${name}`;
    const tone = colour(name);
    nodes.push({id: branchId, type: 'knowledge', data: {kind: 'branch', label: name.replaceAll('-', ' '), colour: tone}, position: {x: 0, y: 0}});
    edges.push({id: `root-${branchId}`, source: 'root', target: branchId, style: {stroke: tone, strokeWidth: 2}});
    graph.setNode(branchId, {width: 150, height: 58}); graph.setEdge('root', branchId);
    members.forEach(atom => {
      const id = `atom:${atom.id}`;
      nodes.push({id, type: 'knowledge', data: {...atom, kind: 'atom', label: atom.title, colour: tone}, position: {x: 0, y: 0}});
      edges.push({id: `${branchId}-${id}`, source: branchId, target: id, style: {stroke: `${tone}99`, strokeWidth: 1.4}});
      graph.setNode(id, {width: 245, height: 76}); graph.setEdge(branchId, id);
    });
  });
  dagre.layout(graph);
  return {
    nodes: nodes.map(node => {
      const pos = graph.node(node.id);
      return {...node, position: {x: pos.x - (node.data.kind === 'atom' ? 122 : 75), y: pos.y - 30}};
    }), edges,
  };
}

function App() {
  const [atoms, setAtoms] = useState([]);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [term, setTerm] = useState('');
  const [direction, setDirection] = useState('LR');
  const [selected, setSelected] = useState(null);
  const [status, setStatus] = useState('Cargando la base de conocimiento…');
  const {fitView} = useReactFlow();

  const draw = useCallback((items, layout) => {
    const next = buildGraph(items, layout);
    setNodes(next.nodes); setEdges(next.edges);
    setTimeout(() => fitView({padding: .14, duration: 300}), 80);
  }, [fitView, setEdges, setNodes]);

  const search = useCallback(async (value = '') => {
    setStatus('Consultando SLDB…');
    const response = await fetch(`/api/search?q=${encodeURIComponent(value)}`);
    const data = await response.json();
    if (!response.ok) { setStatus(data.detail || 'No se pudo consultar SLDB.'); return; }
    setAtoms(data.atoms); setSelected(data.atoms[0] || null); draw(data.atoms, direction);
    setStatus(`${data.atoms.length} átomos · ${value ? `resultado para “${value}”` : 'vista completa'}`);
  }, [direction, draw]);

  useEffect(() => { search(); }, []);
  useEffect(() => { if (atoms.length) draw(atoms, direction); }, [direction]);
  const topics = useMemo(() => [...new Set(atoms.flatMap(atom => atom.tags.filter(tag => tag.startsWith('topic:'))))].sort(), [atoms]);
  const onNodeClick = (_, node) => { if (node.data.kind === 'atom') setSelected(node.data); };

  return html`<main className="shell">
    <header><div><p className="eyebrow">VISOR DE CONOCIMIENTO · SLDB</p><h1>Tutor APOE</h1><p className="subtitle">Teoría APOS, sin chatbot ni modelo generativo.</p></div>
      <div className="help">${status}<br/><span>La KB se edita en archivos Markdown; esta vista es solo de lectura.</span></div></header>
    <section className="toolbar"><form onSubmit=${event => {event.preventDefault(); search(term)}}><input value=${term} onInput=${event => setTerm(event.target.value)} placeholder="Buscar texto o tag: topic:schema"/><button>Buscar</button><button type="button" className="secondary" onClick=${() => {setTerm(''); search('')}}>Limpiar</button></form>
      <div className="layouts"><button className=${direction === 'LR' ? 'active' : ''} onClick=${() => setDirection('LR')}>Árbol</button><button className=${direction === 'TB' ? 'active' : ''} onClick=${() => setDirection('TB')}>Vertical</button></div></section>
    <section className="topics"><span>Temas visibles</span>${topics.slice(0, 14).map(tag => html`<button key=${tag} onClick=${() => {setTerm(tag); search(tag)}}>${tag.replace('topic:', '')}</button>`)}</section>
    <section className="workspace"><div className="canvas"><${ReactFlow} nodes=${nodes} edges=${edges} nodeTypes=${nodeTypes} onNodesChange=${onNodesChange} onEdgesChange=${onEdgesChange} onNodeClick=${onNodeClick} fitView proOptions=${{hideAttribution: true}} minZoom=${.08} maxZoom=${1.8}><${Background} gap=${24} color="rgba(212,165,116,.14)"/><${Controls}/><${MiniMap} nodeColor=${node => node.data.colour} maskColor="rgba(7, 11, 18, .75)"/></${ReactFlow}></div>
      <aside className="detail"><p className="eyebrow">ÁTOMO SELECCIONADO</p>${selected ? html`<h2>${selected.title}</h2><div className="chips">${selected.tags.map(tag => html`<span key=${tag}>${tag}</span>`)}</div><h3>Respuesta</h3><p>${selected.answer || 'Sin respuesta.'}</p>${selected.provenance && html`<><h3>Procedencia</h3><p>${selected.provenance}</p></>}<footer>${selected.path}</footer>` : html`<p>Selecciona un átomo en el mapa.</p>`}</aside>
    </section>
  </main>`;
}
createRoot(document.getElementById('root')).render(html`<${ReactFlowProvider}><${App}/></${ReactFlowProvider}>`);
