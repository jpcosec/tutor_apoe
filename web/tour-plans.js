/* Selectors refer to live controls. Readiness is based on completed app state. */
(() => {
  window.TutorTourPlans = (view, doc) => {
    const q = selector => doc.querySelector(selector);
    const at = selector => () => q(selector);
    if (view === 'scratch') return [
      {target:at('#scratchTitle'), title:'Dale un nombre a tu idea', text:'Cada borrador tiene un título propio. Los borradores se guardan en este navegador y puedes retomarlos desde la lista lateral.'},
      {target:at('#scratchBody'), title:'Un espacio libre para pensar', text:'Escribe notas, preguntas o fragmentos. Se guardan automáticamente mientras escribes. Puedes usar Markdown y los botones de formato. Nada se envía al modelo ni entra a la base de conocimiento.'},
      {target:at('#newNote'), title:'Separa tus ideas en borradores', text:'Crea otra nota cuando quieras explorar un tema distinto. Cambiar de borrador conserva lo que ya escribiste.'},
      {target:at('#exportNote'), title:'Llévate una copia', text:'Este botón descarga el borrador actual como archivo Markdown. Úsalo para respaldar tus notas o compartirlas fuera del tutor.'}
    ];
    if (view === 'chat') return [
      {target:at('#input'), title:'Haz tu primera pregunta', text:'Escribe aquí una pregunta sobre la teoría. Puedes pedir una explicación, comparar conceptos o solicitar un ejemplo. El recorrido no envía mensajes por ti.'},
      {target:at('#send'), title:'Conversar con fundamento', text:'Este botón envía tu pregunta al tutor. La respuesta se construye con los átomos seleccionados. Puedes seguir preguntando dentro de la misma conversación.'},
      {target:at('#sidebarToggle'), title:'Consulta la evidencia', text:'Abre este panel y selecciona una respuesta para inspeccionar los átomos que la sostienen. Las citas de la respuesta también abren sus fuentes.'},
      {target:at('#newChatBtn'), title:'Empieza otro hilo cuando quieras', text:'Aquí puedes iniciar otra conversación. Para explorar nuevas fuentes o navegar el mapa, utiliza las pestañas superiores.'}
    ];
    if (view === 'graph') return [
      {target:at('.toolbar form'), title:'Encuentra un concepto', text:'Busca texto o un tag como topic:schema. Buscar usa los átomos fuente y conserva las ramas necesarias para mostrar su jerarquía.'},
      {target:at('.layouts'), title:'Elige cómo mirar el mapa', text:'Cambia la orientación o pulsa «Ver átomos» para mostrar las ideas dentro de cada rama. Estos controles no modifican el conocimiento.'},
      {target:at('.react-flow__controls'), title:'Acércate y explora', text:'Usa el zoom o «Ajustar» para recorrer el árbol. Selecciona una tarjeta de átomo para consultar o editar su contenido y procedencia. Guardar sí modifica su archivo fuente.'}
    ];
    const adapter = doc.defaultView.tutorGuide;
    if (!adapter) return [];
    const state = () => adapter.state();
    const stage = number => () => adapter.go(number);
    const working = () => state().busy;
    const step = options => ({busy:working, ...options});
    return [
      {target:at('#newPackage'), title:'Un paquete, una fuente', text:'Empieza aquí para crear otro paquete, o abre uno guardado en la biblioteca. Cada PDF o página conserva su propio árbol. El recorrido no crea ni borra paquetes.'},
      step({prepare:stage(0), target:at('#title'), title:'Ponle un nombre', text:'Escribe un nombre que te ayude a reconocer el libro o capítulo. Si abriste un paquete existente, puedes continuar con él.', ready:()=>state().named || state().source, wait:'Escribe un nombre o abre un paquete guardado para continuar.'}),
      step({prepare:stage(0), target:at('.type-tabs'), title:'Elige PDF o página', text:'Estos botones cambian el tipo de fuente. Puedes cargar un PDF con texto seleccionable o usar la dirección final de una página pública.'}),
      step({prepare:stage(0), target:()=>q(state().kind === 'pdf' ? '#pdfField' : '#urlField'), title:'Selecciona tu fuente', text:'Usa este control para seleccionar el PDF o pegar la URL. Puedes arrastrar un PDF hasta la zona resaltada. Para libros grandes, trabaja por capítulos.', ready:()=>state().inputReady || state().source, wait:'Selecciona un PDF, introduce una URL válida o abre un paquete existente.'}),
      step({prepare:stage(0), target:()=>q(working() ? '#status' : '#importSource'), title:'Incorpora la fuente', text:'Pulsa «Incorporar y continuar» para extraer el texto. No se generarán ideas hasta el siguiente paso. Si ya tienes un paquete abierto, puedes continuar sin incorporar otra fuente.', ready:()=>state().source, auto:true, wait:'Usa el botón resaltado para incorporar la fuente. El recorrido avanzará al terminar.'}),
      step({prepare:stage(1), target:()=>q(working() ? '#status' : state().outline ? '#outline' : '#summarize'), title:'Genera el resumen estructural', text:'Pulsa «Generar átomos estructurales». El modelo leerá la fuente y preparará ideas con sus referencias. Si el resumen ya existe, puedes pasar a revisarlo.', ready:()=>state().outline, auto:true, wait:'Genera el resumen para continuar. Puede tardar varios minutos.'}),
      step({prepare:stage(1), target:at('#outline .atom-card'), title:'Revisa una idea y su respaldo', text:'Lee esta tarjeta. Sus referencias abren el fragmento original y «Editar átomo» permite ajustar la afirmación. Revisa el resumen antes de condensarlo; tus cambios se guardarán al crear el grafo.'}),
      step({prepare:stage(2), target:()=>q(working() ? '#status' : state().graph ? '#graph' : '#condense'), title:'Condensa y conecta', text:'Pulsa «Condensar y crear el grafo». Se combinarán las ideas del resumen conservando sus referencias. No se añade conocimiento de otras fuentes.', ready:()=>state().graph, auto:true, wait:'Crea el grafo para continuar. Avanzaremos cuando esté listo.'}),
      step({prepare:stage(2), target:()=>q('#graph svg g') || q('#graph'), title:'Sigue el origen de un concepto', text:'Selecciona un nodo real del mapa. El panel muestra su síntesis, los átomos de origen y sus fuentes. El zoom y «Editar conceptos y relaciones» te permiten revisarlo con calma.'}),
      step({prepare:stage(3), target:()=>q(working() ? '#status' : state().active ? '#chatReady' : '#activate'), title:'Activa el paquete revisado', text:'Usa «Activar este paquete» cuando el mapa represente bien la fuente. Se prepara una KB independiente para conversar. Si ya está activo, puedes continuar.', ready:()=>state().active, auto:true, wait:'Activa el paquete con el botón resaltado para habilitar su conversación.'}),
      step({prepare:stage(3), target:at('#question'), title:'Conversa con esta fuente', text:'Escribe una pregunta aquí o elige una sugerencia. Puedes volver al resumen o al mapa cuando quieras. Terminar el recorrido no envía tu pregunta ni modifica el paquete.'})
    ];
  };
})();
