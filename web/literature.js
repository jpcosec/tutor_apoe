const $ = selector => document.querySelector(selector);

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'No se pudo completar la operación.');
  return data;
}

function renderSource(source) {
  const article = document.createElement('article');
  article.className = 'source';
  const title = document.createElement('h3'); title.textContent = source.title;
  article.append(title);
  const meta = document.createElement('p'); meta.className = 'meta';
  meta.textContent = [source.authors, source.year, source.topic].filter(Boolean).join(' · ') || 'Sin datos complementarios.';
  article.append(meta);
  if (source.citation) { const p = document.createElement('p'); p.textContent = source.citation; article.append(p); }
  if (source.location) { const p = document.createElement('p'); p.className = 'location'; p.textContent = source.location; article.append(p); }
  if (source.notes) { const p = document.createElement('p'); p.textContent = 'Notas: ' + source.notes; article.append(p); }
  return article;
}

async function load() {
  const module = await request('/api/literature');
  $('#description').textContent = module.description;
  const sources = Array.isArray(module.sources) ? module.sources : [];
  for (const [id, type] of [['books', 'book'], ['research', 'research']]) {
    const target = $('#' + id); target.replaceChildren();
    const entries = sources.filter(source => source.source_type === type);
    if (!entries.length) { const p = document.createElement('p'); p.className = 'empty'; p.textContent = 'Aún no hay fuentes registradas.'; target.append(p); }
    else target.append(...entries.map(renderSource));
  }
}

$('#source-form').onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(['source-type', 'title', 'authors', 'year', 'topic', 'citation', 'location', 'notes'].map(id => [id.replace('source-type', 'source_type'), $('#' + id).value]));
  try {
    await request('/api/literature', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
    event.target.reset(); $('#status').textContent = 'Referencia guardada en el catálogo. Puedes cargar la fuente para proponer átomos cuando el archivo esté disponible.';
    await load();
  } catch (error) { $('#status').textContent = error.message; }
};

load().catch(error => { $('#status').textContent = error.message; });
