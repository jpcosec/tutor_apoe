const $ = selector => document.querySelector(selector);
const expertId = location.pathname.split('/').filter(Boolean)[1] || null;
let conversationId = null;
let hostProtocol = null;

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
  hostProtocol = protocol;
  $('#protocol-title').value = protocol.title || '';
  $('#protocol-instructions').value = protocol.instructions || '';
  $('#protocol-questions').value = (protocol.questions || []).map(question => typeof question === 'string' ? question : question.prompt).join('\n');
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
        questions: $('#protocol-questions').value.split('\n').map(value => value.trim()).filter(Boolean).map((value, index) => {
          const previous = hostProtocol.questions && hostProtocol.questions[index];
          return previous && typeof previous === 'object' ? {...previous, prompt: value} : value;
        }),
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
    $('#opening-text').textContent = data.protocol.opening || 'La entrevista solicita conformidad antes de comenzar.';
    if (!data.protocol.questions.length) {
      $('#question-text').textContent = 'La coordinación aún no configuró el protocolo. Recibirás preguntas cuando esté listo.';
      return;
    }
    const showQuestion = question => {
      $('#question-title').textContent = question.id + ' · ' + (question.kind === 'followup' ? 'Repregunta' : 'Pregunta') + ' ' + question.position;
      $('#question-text').textContent = question.prompt;
      $('#answer-form').hidden = false;
      $('#pause').hidden = false;
      $('#close-early').hidden = false;
    };
    const showValidation = synthesis => {
      $('#validation-card').hidden = false;
      $('#synthesis').textContent = synthesis.map(item => item.question_id + ': ' + item.answer).join('\n\n');
    };
    const paused = (data.conversations || []).find(item => item.status === 'paused');
    if (paused) {
      $('#opening-card').hidden = true;
      $('#resume').hidden = false;
      $('#question-text').textContent = 'Hay una entrevista pausada. Puedes reanudarla desde la siguiente pregunta pendiente.';
      $('#resume').onclick = async () => {
        try {
          const result = await request('/api/experts/' + encodeURIComponent(expertId) + '/resume', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({conversation_id: paused.id})});
          conversationId = result.conversation.id;
          $('#resume').hidden = true;
          showQuestion(result.next_question);
        } catch (error) { status(error.message, true); }
      };
      return;
    }
    const start = async consent => {
      try {
        const started = await request('/api/experts/' + encodeURIComponent(expertId) + '/start', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({participant_code: $('#participant-code').value, consent})});
        conversationId = started.conversation.id;
        $('#opening-card').hidden = true;
        if (consent) showQuestion(started.question);
        else $('#question-text').textContent = 'La participación fue declinada. La sesión se cerró sin preguntas.';
      } catch (error) { status(error.message, true); }
    };
    $('#opening-form').onsubmit = event => { event.preventDefault(); start($('#consent').checked); };
    $('#decline').onclick = () => start(false);
    $('#answer-form').onsubmit = async event => {
      event.preventDefault();
      try {
        const related = $('#related-questions').value.split(',').map(item => item.trim()).filter(Boolean);
        const result = await request('/api/experts/' + encodeURIComponent(expertId) + '/responses', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({conversation_id: conversationId, answer: $('#answer').value, coverage: $('#coverage').value, related_questions: related})});
        $('#answer').value = '';
        if (result.next_question) {
          showQuestion(result.next_question);
        } else {
          $('#question-title').textContent = 'Revisión de síntesis';
          $('#question-text').textContent = 'Revisa la síntesis antes de validar o cerrar la entrevista.';
          $('#answer-form').hidden = true;
          $('#pause').hidden = true;
          $('#close-early').hidden = true;
          showValidation(result.conversation.responses);
        }
      } catch (error) { status(error.message, true); }
    };
    $('#pause').onclick = async () => {
      try {
        const result = await request('/api/experts/' + encodeURIComponent(expertId) + '/pause', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({conversation_id: conversationId})});
        $('#answer-form').hidden = true;
        $('#pause').hidden = true;
        $('#question-text').textContent = 'Entrevista pausada. La siguiente pregunta al reanudar será: ' + result.next_question.prompt;
      } catch (error) { status(error.message, true); }
    };
    const close = async (validated, endedEarly) => {
      try {
        const result = await request('/api/experts/' + encodeURIComponent(expertId) + '/validate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({conversation_id: conversationId, validated, ended_early: endedEarly, corrections: $('#corrections').value})});
        $('#validation-card').hidden = true;
        $('#question-title').textContent = 'Entrevista cerrada';
        const message = validated ? 'La síntesis fue validada y quedó disponible para revisión del módulo experto.' : 'La entrevista quedó cerrada con sus reservas de validación registradas.';
        const link = document.createElement('a');
        link.href = '/api/experts/' + encodeURIComponent(expertId) + '/export?conversation=' + encodeURIComponent(conversationId);
        link.textContent = 'Descargar registro para revisión e ingreso al Tutor APOE';
        $('#question-text').replaceChildren(document.createTextNode(message + ' '), link);
      } catch (error) { status(error.message, true); }
    };
    $('#validate').onclick = () => close(true, false);
    $('#close-unvalidated').onclick = () => close(false, false);
    $('#close-early').onclick = () => close(false, true);
  } catch (error) { status(error.message, true); }
}

expertId ? expertView() : hostView();
