/* Vista uno: texto de la fuente a la izquierda con resaltado, átomos anclados a la derecha, hover cruzado.
   Deep links: /surface?page=N · /surface?atom=<id> (salta al primer fragmento anclado) · /surface?chunk=<id>. */
(() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const state = {outline: null, page: null, pageData: null, target: {atom: null, chunk: null}};

  async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${res.status} ${url}`);
    return res.json();
  }

  function setUrl(params) {
    const url = new URL(location.href);
    ['page', 'atom', 'chunk'].forEach(k => url.searchParams.delete(k));
    Object.entries(params).forEach(([k, v]) => { if (v != null) url.searchParams.set(k, v); });
    history.replaceState(null, '', url.toString());
  }

  // ---------- navegación: esquema y mapa de páginas ----------
  function renderOutline() {
    const o = state.outline;
    $('sourceTitle').textContent = o.title || o.source || 'Fuente';
    $('pageTotal').textContent = `/ ${o.n_pages}`;
    $('pageInput').max = o.n_pages;
    const map = $('pageMap');
    map.innerHTML = '';
    for (const p of o.pages) {
      const cell = document.createElement('span');
      cell.className = `cell ${p.n_atoms ? 'has' : ''} ${p.page === state.page ? 'current' : ''}`;
      cell.title = `p. ${p.page} · ${p.n_chunks} fragmentos · ${p.n_atoms} átomos`;
      cell.dataset.page = p.page;
      cell.addEventListener('click', () => go(p.page));
      map.appendChild(cell);
    }
    const out = $('outline');
    out.innerHTML = '';
    for (const e of o.entries) {
      const btn = document.createElement('button');
      const section = state.pageData && state.pageData.section;
      btn.className = `entry l${Math.min(e.level, 3)} ${section && section.number === e.number ? 'active' : ''}`;
      const num = /^\d/.test(e.number) ? `${e.number} ` : '';
      btn.innerHTML = `${esc(num)}${esc(e.title)}<small>p. ${e.page_start}${e.page_end !== e.page_start ? `–${e.page_end}` : ''}</small>`;
      btn.addEventListener('click', () => go(e.page_start));
      out.appendChild(btn);
    }
  }

  function markCurrent() {
    document.querySelectorAll('#pageMap .cell').forEach(c => c.classList.toggle('current', Number(c.dataset.page) === state.page));
    const section = state.pageData && state.pageData.section;
    document.querySelectorAll('#outline .entry').forEach((b, i) => b.classList.toggle('active', !!section && state.outline.entries[i].number === section.number));
  }

  // ---------- página: fragmentos con resaltado ----------
  function excerptRegex(excerpt) {
    const words = excerpt.trim().split(/\s+/).map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    return new RegExp(words.join('[\\s\\-\\u00AD]*'), 'i');
  }

  function renderChunk(chunk, atoms) {
    const byId = Object.fromEntries(atoms.map(a => [a.id, a]));
    let html = esc(chunk.text);
    // resaltar los excerpts de los átomos anclados a este fragmento (sobre el texto escapado)
    for (const id of chunk.atoms) {
      const atom = byId[id];
      const anchor = atom && atom.anchors.find(a => a.chunk_id === chunk.chunk_id && a.excerpt);
      if (!anchor) continue;
      const re = excerptRegex(esc(anchor.excerpt));
      const m = html.match(re);
      if (m) html = html.replace(re, `<mark data-atom="${esc(id)}">${m[0]}</mark>`);
    }
    const pins = chunk.atoms.map(id => `<span class="pin" data-atom="${esc(id)}" title="${esc(byId[id] ? byId[id].title : id)}"></span>`).join('');
    return `<div class="chunk ${chunk.atoms.length ? 'has' : ''}" id="chunk-${esc(chunk.chunk_id)}" data-chunk="${esc(chunk.chunk_id)}" data-atoms="${esc(chunk.atoms.join(','))}"><span class="cid">${esc(chunk.chunk_id.replace(/^.*-chunk-/, '#'))}</span>${html}<span class="pins">${pins}</span></div>`;
  }

  function statusChip(status) {
    return {anchored: '<span class="chip ok">anclado</span>', unanchored: '<span class="chip warn">sin respaldo</span>', expert: '<span class="chip">experto</span>', pending: '<span class="chip">sin evaluar</span>', derived: '<span class="chip">derivado</span>'}[status] || '';
  }

  function renderCard(atom) {
    const chunks = atom.anchors.map(a => a.chunk_id);
    return `<div class="card" data-atom="${esc(atom.id)}" data-chunks="${esc(chunks.join(','))}"><div class="name">${esc(atom.title)}</div><div class="cite">${esc(atom.citation)}</div><div class="chips">${statusChip(atom.status)}${(atom.tags || []).filter(t => t.startsWith('topic:')).map(t => `<span class="chip">${esc(t.slice(6))}</span>`).join('')}</div><div class="ids">${esc(atom.id)}</div></div>`;
  }

  function renderPage() {
    const d = state.pageData;
    $('pageTitle').textContent = `Página ${d.page}`;
    $('pageInput').value = d.page;
    const s = d.section;
    $('sectionLabel').textContent = s ? `${/^\d/.test(s.number) ? s.number + ' · ' : ''}${s.title}` : 'Fuera del esquema';
    $('pageMeta').textContent = `${d.chunks.length} fragmentos · ${d.atoms.length} átomos`;
    $('prevPage').disabled = d.prev == null; $('nextPage').disabled = d.next == null;
    $('pageBody').innerHTML = d.chunks.map(c => renderChunk(c, d.atoms)).join('') || '<div class="empty">Página sin texto.</div>';
    $('atomList').innerHTML = d.atoms.map(renderCard).join('') || '<div class="empty">Ningún átomo se verifica en esta página. Es una página sin cubrir: candidata para el compilador.</div>';
    $('atomsMeta').textContent = d.atoms.length ? 'Pasa el cursor por un átomo para ver dónde se verifica; clic para abrirlo.' : `p. ${d.page} sin átomos anclados.`;
    markCurrent();
    wireHover();
    if (state.target.chunk) focusChunk(state.target.chunk, state.target.atom);
    state.target = {atom: null, chunk: null};
  }

  function focusChunk(chunkId, atomId) {
    const el = document.getElementById(`chunk-${chunkId}`);
    if (!el) return;
    el.classList.add('target');
    el.scrollIntoView({block: 'center', behavior: 'smooth'});
    if (atomId) setHot(atomId, true);
    setTimeout(() => { el.classList.remove('target'); if (atomId) setHot(atomId, false); }, 2600);
  }

  // ---------- hover cruzado ----------
  function setHot(atomId, on) {
    document.querySelectorAll(`.card[data-atom="${CSS.escape(atomId)}"]`).forEach(c => c.classList.toggle('hot', on));
    document.querySelectorAll(`mark[data-atom="${CSS.escape(atomId)}"], .pin[data-atom="${CSS.escape(atomId)}"]`).forEach(m => m.classList.toggle('hot', on));
    document.querySelectorAll('.chunk').forEach(ch => {
      const atoms = (ch.dataset.atoms || '').split(',').filter(Boolean);
      ch.classList.toggle('hot', on && atoms.includes(atomId));
    });
  }

  function setHotChunk(chunkId, on) {
    const ch = document.getElementById(`chunk-${chunkId}`);
    if (!ch) return;
    const atoms = (ch.dataset.atoms || '').split(',').filter(Boolean);
    ch.classList.toggle('hot', on && atoms.length > 0);
    document.querySelectorAll('.card').forEach(card => {
      const mine = atoms.includes(card.dataset.atom);
      card.classList.toggle('hot', on && mine);
      card.classList.toggle('dim', on && atoms.length > 0 && !mine);
    });
  }

  function wireHover() {
    document.querySelectorAll('.card').forEach(card => {
      card.addEventListener('mouseenter', () => setHot(card.dataset.atom, true));
      card.addEventListener('mouseleave', () => setHot(card.dataset.atom, false));
      card.addEventListener('click', () => openAtom(card.dataset.atom));
    });
    document.querySelectorAll('.chunk').forEach(ch => {
      ch.addEventListener('mouseenter', () => setHotChunk(ch.dataset.chunk, true));
      ch.addEventListener('mouseleave', () => setHotChunk(ch.dataset.chunk, false));
    });
    document.querySelectorAll('mark[data-atom], .pin[data-atom]').forEach(m => {
      m.addEventListener('mouseenter', e => { e.stopPropagation(); setHot(m.dataset.atom, true); });
      m.addEventListener('mouseleave', () => setHot(m.dataset.atom, false));
      m.addEventListener('click', e => { e.stopPropagation(); openAtom(m.dataset.atom); });
    });
  }

  // ---------- inspector de átomo ----------
  async function openAtom(atomId) {
    let atom;
    try { atom = await getJSON(`/api/surface/atom/${encodeURIComponent(atomId)}`); } catch { return; }
    $('modalTitle').textContent = atom.title;
    const anchors = atom.anchors.map(a => `<div class="anchor" data-chunk="${esc(a.chunk_id)}" data-page="${a.page}"><div>p. ${a.page} · <code>${esc(a.chunk_id.replace(/^.*-chunk-/, '#'))}</code>${a.noul != null ? ` · noul ${a.noul}` : ''}</div>${a.excerpt ? `<div class="q">«${esc(a.excerpt)}»</div>` : ''}</div>`).join('');
    $('modalBody').innerHTML = `<div>${marked.parse(atom.answer || '')}</div><div><strong>Procedencia:</strong> ${esc(atom.citation)} ${statusChip(atom.status)}</div><div class="chips">${(atom.tags || []).map(t => `<span class="chip">${esc(t)}</span>`).join('')}</div>${anchors ? `<div><strong>Tramos que lo anclan</strong></div>${anchors}` : '<div class="empty">Sin tramos anclados en la fuente.</div>'}<div class="links"><a class="linkish" href="${esc(atom.graph_url)}" target="_blank">ver en el grafo</a><a class="linkish" href="${esc(atom.chat_url)}" target="_blank">preguntar en el chat</a><span class="linkish">${esc(atom.id)}</span></div>`;
    $('modalBody').querySelectorAll('.anchor').forEach(el => el.addEventListener('click', () => { closeModal(); state.target = {atom: atom.id, chunk: el.dataset.chunk}; go(Number(el.dataset.page)); }));
    $('modalBackdrop').classList.add('open');
    setUrl({page: state.page, atom: atom.id});
  }
  function closeModal() { $('modalBackdrop').classList.remove('open'); setUrl({page: state.page}); }

  // ---------- carga ----------
  async function go(page) {
    if (!page) return;
    try {
      state.pageData = await getJSON(`/api/surface/page/${page}`);
    } catch {
      $('pageBody').innerHTML = `<div class="empty">No hay texto para la página ${page}.</div>`;
      return;
    }
    state.page = page;
    setUrl({page});
    renderPage();
  }

  async function boot() {
    state.outline = await getJSON('/api/surface/outline');
    const q = new URLSearchParams(location.search);
    renderOutline();
    if (q.get('atom')) {
      try {
        const atom = await getJSON(`/api/surface/atom/${encodeURIComponent(q.get('atom'))}`);
        if (atom.first_page) { state.target = {atom: atom.id, chunk: atom.first_chunk}; await go(atom.first_page); openAtom(atom.id); return; }
        await go(state.outline.pages[0] && state.outline.pages[0].page); openAtom(atom.id); return;
      } catch { /* cae a la primera página */ }
    }
    if (q.get('chunk')) {
      try {
        const chunk = await getJSON(`/api/surface/chunk/${encodeURIComponent(q.get('chunk'))}`);
        state.target = {atom: null, chunk: chunk.chunk_id}; await go(chunk.page); return;
      } catch { /* idem */ }
    }
    const first = state.outline.entries.find(e => e.number === '1');
    await go(Number(q.get('page')) || (first ? first.page_start : (state.outline.pages[0] || {}).page));
  }

  $('prevPage').addEventListener('click', () => state.pageData && go(state.pageData.prev));
  $('nextPage').addEventListener('click', () => state.pageData && go(state.pageData.next));
  $('pageInput').addEventListener('change', () => go(Number($('pageInput').value)));
  $('modalClose').addEventListener('click', closeModal);
  $('modalBackdrop').addEventListener('click', e => { if (e.target === $('modalBackdrop')) closeModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); if (e.target.tagName === 'INPUT') return; if (e.key === 'ArrowLeft') $('prevPage').click(); if (e.key === 'ArrowRight') $('nextPage').click(); });
  boot().catch(err => { $('pageBody').innerHTML = `<div class="empty">No se pudo cargar la superficie: ${esc(err.message)}</div>`; });
})();
