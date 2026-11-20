const $ = selector => document.querySelector(selector);
const expertId = location.pathname.split('/').filter(Boolean)[1] || null;
let conversationId = null;

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'No se pudo completar la operación.');
  return data;
}

function status(message, warning = false) {
  $('#status').textContent = message;
  $('#status').classList.toggle('warning', warning);
}

function protocolIntoForm(protocol) {
  $('#protocol-title').value = protocol.title || '';
  $('#protocol-instructions').value = protocol.instructions || '';
  $('#protocol-questions').value = (protocol.questions || []).join('\n');
}

async function loadModule() {
  const module = await request('/api/expert-module');
  const target = $('#module-summary');
  if (!module.experts.length) {
    target.textContent = 'Aún no hay especialistas invitados.';
    return;
  }
  target.replaceChildren(...module.experts.map(item => {
    const row = document.createElement('div');
    row.className = 'module-item';
    row.textContent = item.name + ': ' + item.conversations + ' conversación(es), ' + item.responses + ' respuesta(s).';
    return row;
  }));
}

async function hostView() {
  $('#host').hidden = false;
  protocolIntoForm(await request('/api/expert-protocol'));
  await loadModule();
  $('#protocol-form').onsubmit = async event => {
    event.preventDefault();
    try {
      const protocol = await request('/api/expert-protocol', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
        title: $('#protocol-title').value,
        instructions: $('#protocol-instructions').value,
        questions: $('#protocol-questions').value.split('\n').map(value => value.trim()).filter(Boolean),
      })});
      protocolIntoForm(protocol);
      status('Protocolo guardado. Ya puedes crear enlaces para especialistas.');
    } catch (error) { status(error.message, true); }
  };
  $('#expert-form').onsubmit = async event => {
    event.preventDefault();
    try {
      const data = await request('/api/experts', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: $('#expert-name').value})});
      const invite = $('#invite');
      invite.hidden = false;
      invite.textContent = 'Enlace para ' + data.expert.name + ':\n' + data.link + '\n\nInstrucciones: abre el enlace, lee el protocolo y responde una pregunta a la vez. Tus respuestas quedarán en tu repositorio personal.';
      event.target.reset();
      await loadModule();
    } catch (error) { status(error.message, true); }
  };
}

async function expertView() {
  $('#expert').hidden = false;
  try {
    const data = await request('/api/experts/' + encodeURIComponent(expertId));
    $('#expert-name-title').textContent = data.expert.name;
    $('#protocol-instructions-view').textContent = data.protocol.instructions;
    if (!data.protocol.questions.length) {
      $('#question-text').textContent = 'La coordinación aún no configuró el protocolo. Recibirás preguntas cuando esté listo.';
      return;
    }
    $('#start').hidden = false;
    $('#start').onclick = async () => {
      try {
        const started = await request('/api/experts/' + encodeURIComponent(expertId) + '/start', {method: 'POST'});
        conversationId = started.conversation.id;
        $('#question-title').textContent = 'Pregunta 1';
        $('#question-text').textContent = started.question;
        $('#answer-form').hidden = false;
        $('#start').hidden = true;
      } catch (error) { status(error.message, true); }
    };
    $('#answer-form').onsubmit = async event => {
      event.preventDefault();
      try {
        const result = await request('/api/experts/' + encodeURIComponent(expertId) + '/responses', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({conversation_id: conversationId, answer: $('#answer').value})});
        $('#answer').value = '';
        if (result.next_question) {
          $('#question-title').textContent = 'Pregunta ' + (result.conversation.question_index + 1);
          $('#question-text').textContent = result.next_question;
        } else {
          $('#question-title').textContent = 'Entrevista completada';
          $('#question-text').textContent = 'Tus respuestas quedaron guardadas en tu repositorio personal y reunidas en el Módulo APOE.';
          $('#answer-form').hidden = true;
        }
      } catch (error) { status(error.message, true); }
    };
  } catch (error) { status(error.message, true); }
}

expertId ? expertView() : hostView();
