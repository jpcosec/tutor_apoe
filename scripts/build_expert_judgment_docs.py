#!/usr/bin/env python3
"""Genera los instrumentos Word para la validacion experta del Tutor APOE."""

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


OUT = Path("docs/validacion-experta")
NAVY = "17365D"
BLUE = "D9EAF7"
PALE = "F3F6F9"
GRID = "D9D9D9"


def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def set_cell_margins(cell, top=90, start=110, bottom=90, end=110):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for side, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_borders(table):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = qn(f"w:{edge}")
        el = borders.find(tag)
        if el is None:
            el = OxmlElement(f"w:{edge}")
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), GRID)


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def write_cell(cell, text, bold=False, color=None, align=None, size=9.5):
    cell.text = ""
    p = cell.paragraphs[0]
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(text)
    r.bold = bold
    r.font.size = Pt(size)
    r.font.name = "Aptos"
    r._element.rPr.rFonts.set(qn("w:ascii"), "Aptos")
    r._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos")
    if color:
        r.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    set_cell_margins(cell)


def base_doc(title, subtitle):
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)

    normal = doc.styles["Normal"]
    normal.font.name = "Aptos"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Aptos")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos")
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.12
    for style_name, size in (("Title", 22), ("Heading 1", 15), ("Heading 2", 12)):
        style = doc.styles[style_name]
        style.font.name = "Aptos Display" if style_name == "Title" else "Aptos"
        style._element.rPr.rFonts.set(qn("w:ascii"), style.font.name)
        style._element.rPr.rFonts.set(qn("w:hAnsi"), style.font.name)
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.bold = True

    p = doc.add_paragraph(style="Title")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.add_run(title)
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(16)
    r = p.add_run(subtitle)
    r.italic = True
    r.font.size = Pt(11)
    meta = doc.add_paragraph()
    meta.paragraph_format.space_after = Pt(18)
    run = meta.add_run("Tutor APOE  |  Versión para validación por juicio experto  |  Noviembre de 2026")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(89, 89, 89)

    footer = section.footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fr = fp.add_run("Tutor APOE")
    fr.font.size = Pt(8.5)
    fr.font.color.rgb = RGBColor(89, 89, 89)
    return doc


def heading(doc, text, level=1):
    p = doc.add_paragraph(text, style=f"Heading {level}")
    p.paragraph_format.space_before = Pt(12 if level == 1 else 8)
    p.paragraph_format.space_after = Pt(5)
    return p


def para(doc, text, bold_lead=None):
    p = doc.add_paragraph()
    if bold_lead and text.startswith(bold_lead):
        p.add_run(bold_lead).bold = True
        p.add_run(text[len(bold_lead):])
    else:
        p.add_run(text)
    return p


def bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(item)


def table(doc, headers, rows, widths=None, font_size=9.2):
    t = doc.add_table(rows=1, cols=len(headers))
    t.autofit = False
    t.style = "Table Grid"
    set_borders(t)
    for idx, h in enumerate(headers):
        cell = t.rows[0].cells[idx]
        shade(cell, NAVY)
        write_cell(cell, h, bold=True, color="FFFFFF", align=WD_ALIGN_PARAGRAPH.CENTER, size=font_size)
        if widths:
            cell.width = Inches(widths[idx])
    set_repeat_table_header(t.rows[0])
    for i, row in enumerate(rows):
        cells = t.add_row().cells
        for j, val in enumerate(row):
            if widths:
                cells[j].width = Inches(widths[j])
            if i % 2 == 1:
                shade(cells[j], PALE)
            write_cell(cells[j], str(val), size=font_size)
    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    return t


ITEMS = [
    ("V01", "Naturaleza y alcance", "La caracterización de APOE como teoría de construcciones mentales, en relación con la interacción social que favorece el aprendizaje, es pertinente para orientar las respuestas del Tutor APOE.", "P01"),
    ("V02", "Fundamento de abstracción reflexiva", "La relación propuesta entre abstracción reflexiva y construcción de conocimiento matemático está formulada de manera clara y conceptualmente defendible.", "P02"),
    ("V03", "Organización APOE", "La relación entre acción, proceso, objeto y esquema está suficientemente diferenciada y, al mismo tiempo, organizada como un sistema de construcciones relacionadas.", "P03 a P06"),
    ("V04", "Indicios de acción", "Los criterios para reconocer una acción distinguen adecuadamente el control externo del procedimiento, los apoyos disponibles y la producción del estudiante.", "P03"),
    ("V05", "Indicios de proceso objeto y esquema", "Los criterios propuestos permiten interpretar producciones que evidencien proceso, objeto o esquema sin reducirlos al uso de una palabra, símbolo o algoritmo.", "P04 a P06"),
    ("V06", "Condiciones de interpretación", "El Tutor APOE especifica las condiciones de tarea, apoyos, representaciones y nivel de control que deben considerarse antes de atribuir una construcción.", "P03 a P06"),
    ("V07", "Interiorización frente a fluidez", "El tutor distingue de modo suficiente una interiorización de una ejecución más rápida o memorizada de una acción.", "P07"),
    ("V08", "Mecanismos y operaciones aprendidas", "Los criterios para coordinación, reversión, encapsulación, desencapsulación, tematización y generalización distinguen mecanismos de APOE de la mera aplicación de una operación inversa o de una regla aprendida.", "P08 a P09"),
    ("V09", "Evidencia discriminante", "Para cada interpretación el tutor solicita o propone una tarea de contraste, una interpretación alternativa y el dato que permitiría decidir entre ellas.", "P04 a P09 y P12"),
    ("V10", "Articulación de una DG", "El tutor puede organizar construcciones, mecanismos, prerrequisitos y relaciones en un fragmento de descomposición genética sin presentarlo como una trayectoria única o definitiva.", "P10"),
    ("V11", "Revisión empírica", "El diseño explicita qué producciones, estrategias alternativas o patrones de datos justificarían revisar una construcción, un mecanismo o una relación postulada.", "P11"),
    ("V12", "Integración en casos", "Un caso matemático permite aplicar de manera coherente las capas conceptual, operativa, contrastiva y genética, conservando la evidencia que sustenta cada inferencia.", "P12"),
]


def protocol():
    doc = base_doc("Protocolo de juicio experto", "Validación de la organización conceptual y los criterios interpretativos del Tutor APOE")
    para(doc, "Este protocolo permite valorar, antes de cambiar el tutor, si sus criterios sobre acción, proceso, objeto, esquema, mecanismos y descomposición genética son pertinentes, claros, coherentes y suficientes. El resultado es un cimiento revisable: no reemplaza la contrastación con producciones de estudiantes ni establece una descomposición genética definitiva.")
    heading(doc, "Propósito")
    para(doc, "El panel de especialistas revisa doce ítems organizados en cuatro capas. Cada juicio debe justificarse; los desacuerdos se conservan como evidencia de revisión y no se eliminan por promediación automática.")
    heading(doc, "Alcance y unidad de valoración")
    bullets(doc, [
        "Objeto validado: la organización conceptual y los criterios de interpretación del Tutor APOE.",
        "Unidad de valoración: cada ítem V01 a V12 y el conjunto de tres ítems de cada capa.",
        "No se valida: una trayectoria universal de aprendizaje, una DG definitiva ni inferencias sin evidencia de la tarea y de la producción del estudiante.",
        "Trazabilidad: los doce ítems conservan vínculo con las preguntas P01 a P12 del protocolo LAETEC de origen.",
    ])
    heading(doc, "Estructura de las cuatro capas")
    table(doc, ["Capa", "Función", "Ítems"], [
        ("1 Conceptual", "Delimita la teoría y sus construcciones.", "V01 a V03"),
        ("2 Operativa", "Establece qué evidencias y condiciones permiten interpretar una construcción.", "V04 a V06"),
        ("3 Contrastiva", "Exige alternativas y evidencia discriminante para evitar inferencias apresuradas.", "V07 a V09"),
        ("4 Genética", "Organiza hipótesis revisables de una descomposición genética.", "V10 a V12"),
    ], [1.25, 4.4, 1.0])
    heading(doc, "Procedimiento")
    for n, text in enumerate([
        "Invitar a especialistas que cumplan el perfil de selección y registrar su código, rol y evidencia de experticia.",
        "Entregar una síntesis del Tutor APOE, los doce ítems y la ficha individual. La revisión puede ser asincrónica o mediada por entrevista.",
        "Solicitar una calificación de 1 a 4 para pertinencia, claridad y coherencia de cada ítem. La suficiencia se registra al cierre de cada capa.",
        "Registrar justificación, reformulación propuesta, reserva teórica y referencia declarada cuando corresponda.",
        "Consolidar acuerdos, desacuerdos y problemas de redacción sin atribuir consenso donde no lo haya.",
        "Revisar primero los ítems con calificaciones 1 o 2. Someter la versión ajustada a una segunda ronda breve de confirmación o reserva.",
    ], 1):
        p = doc.add_paragraph(style="List Number")
        p.add_run(text)
    heading(doc, "Escala de valoración")
    table(doc, ["Puntaje", "Interpretación", "Uso en la revisión"], [
        ("1", "No cumple", "Requiere reconsideración sustantiva; conservar la justificación."),
        ("2", "Requiere revisión mayor", "Modificar o reestructurar antes de la segunda ronda."),
        ("3", "Requiere ajuste menor", "Ajustar redacción, delimitación o ejemplo de apoyo."),
        ("4", "Cumple", "Conservar salvo que exista una reserva razonada de otro especialista."),
    ], [0.75, 2.0, 3.9])
    heading(doc, "Criterios de valoración")
    table(doc, ["Criterio", "Pregunta orientadora"], [
        ("Pertinencia", "¿El ítem es necesario para que el Tutor APOE cumpla su propósito?"),
        ("Claridad", "¿El enunciado permite comprender qué debe valorarse sin ambigüedad relevante?"),
        ("Coherencia", "¿El ítem es compatible con la teoría APOE y con las otras capas?"),
        ("Suficiencia", "¿El conjunto de tres ítems de la capa cubre lo necesario o falta un aspecto?"),
    ], [1.4, 5.3])
    heading(doc, "Matriz de ítems")
    table(doc, ["Código", "Capa", "Foco", "Trazabilidad"], [
        (c, "Conceptual" if i < 3 else "Operativa" if i < 6 else "Contrastiva" if i < 9 else "Genética", focus, source)
        for i, (c, focus, _statement, source) in enumerate(ITEMS)
    ], [0.65, 1.3, 3.55, 1.15], font_size=8.8)
    heading(doc, "Reglas de decisión y productos")
    para(doc, "No se usará un promedio como criterio único de aceptación. Una observación fundamentada de baja pertinencia, claridad o coherencia activa revisión cualitativa. La decisión final debe indicar qué cambió, qué se mantuvo, quién formuló una reserva y por qué.")
    bullets(doc, [
        "Matriz de juicios por ítem, criterio y código de especialista.",
        "Registro de acuerdos, desacuerdos, fuentes declaradas y reformulaciones.",
        "Versión revisada de las cuatro capas y un historial que conecte cada cambio con la evidencia del panel.",
        "Lista de criterios operativos candidatos que aún requieren contrastación empírica.",
    ])
    heading(doc, "Confidencialidad y uso")
    para(doc, "Los registros se identifican por código durante el análisis. La identidad, afiliación y datos de contacto se conservan separadamente y sólo se usan para la coordinación de la validación. Antes de participar, cada persona recibe información sobre el propósito, el uso de sus respuestas y su posibilidad de mantener una reserva.")
    doc.save(OUT / "Protocolo_juicio_experto_Tutor_APOE.docx")


def profile():
    doc = base_doc("Perfil del panel experto APOE", "Criterios de selección para la validación conceptual y metodológica del Tutor APOE")
    para(doc, "El panel no debe restringirse a personas con título de matemáticas. El criterio decisivo es la competencia demostrable en teoría APOE y su uso para analizar o diseñar situaciones de aprendizaje matemático. Una formación matemática puede ser relevante, pero por sí sola no acredita esa competencia.")
    heading(doc, "Respuesta operativa")
    para(doc, "No se recomienda seleccionar sólo matemáticos. Se recomienda un panel deliberadamente diverso de investigadores en educación matemática, matemáticos que trabajen explícitamente con APOE, formadores de profesores y personas en formación doctoral o posdoctoral con trabajo supervisado y demostrable en la teoría. La participación se justifica por evidencia de experticia, no por el nombre de la disciplina de origen.")
    heading(doc, "Requisito esencial")
    para(doc, "Toda persona integrante debe demostrar conocimiento de APOE suficiente para distinguir la teoría de una descripción genérica de habilidades. La evidencia puede provenir de publicaciones, tesis, investigación en curso, docencia universitaria fundamentada en APOE, diseño o análisis de tareas con la teoría, o participación sostenida en comunidades académicas especializadas.")
    heading(doc, "Perfiles elegibles")
    table(doc, ["Perfil", "Aporte esperado", "Evidencia mínima sugerida"], [
        ("Investigador o investigadora en educación matemática", "Fundamentación teórica, análisis de evidencias y rigor metodológico.", "Investigación, publicaciones, tesis dirigida o proyectos que empleen APOE."),
        ("Matemático o matemática con trayectoria APOE", "Conexión entre el objeto matemático y la construcción propuesta.", "Uso explícito de APOE en investigación, docencia, diseño o evaluación de tareas."),
        ("Formador o formadora de profesores", "Viabilidad didáctica y lectura de producciones en contextos de enseñanza.", "Trabajo sistemático con APOE y experiencia documentada de formación o investigación."),
        ("Doctorando, doctoranda o posdoctorado", "Perspectiva actualizada y especialización focalizada.", "Tesis o proyecto supervisado que utilice APOE; recomendación de supervisión académica."),
    ], [1.55, 2.55, 2.55], font_size=8.7)
    heading(doc, "Criterios de inclusión")
    bullets(doc, [
        "Conocimiento demostrable de acción, proceso, objeto, esquema, abstracción reflexiva y mecanismos de construcción en APOE.",
        "Capacidad de separar una afirmación teórica, una interpretación de evidencia y una recomendación de diseño.",
        "Experiencia o conocimiento documentado del dominio matemático que se vaya a revisar cuando el juicio trate ejemplos específicos.",
        "Disposición a justificar los juicios, proponer alternativas y sostener desacuerdos razonados.",
        "Declaración de posibles conflictos de interés, por ejemplo, participación en el diseño original del tutor o vínculo de supervisión directa.",
    ])
    heading(doc, "Criterios de exclusión o cautela")
    table(doc, ["Situación", "Decisión recomendada"], [
        ("Título en matemáticas sin evidencia de trabajo o estudio APOE", "No basta como criterio de inclusión; invitar sólo si completa evidencia de formación o experiencia relevante."),
        ("Experiencia docente amplia sin conocimiento demostrable de APOE", "Puede aportar en una consulta posterior de usabilidad, pero no sustituye el juicio teórico especializado."),
        ("Participación directa en el diseño evaluado", "Puede participar como fuente contextual, pero su juicio se registra separadamente y se declara el vínculo."),
        ("Especialista APOE sin familiaridad con el dominio del caso", "Puede revisar la capa conceptual; reservar los ejemplos disciplinares para coevaluación con alguien del dominio."),
    ], [2.8, 3.85])
    heading(doc, "Composición sugerida del panel")
    para(doc, "Como orientación inicial, convocar entre cinco y nueve personas. Buscar equilibrio entre conocimiento de APOE, familiaridad con el dominio matemático revisado, investigación empírica y experiencia formativa. No es una cuota rígida: la composición debe documentar qué perspectiva aporta cada integrante y qué vacío queda abierto.")
    table(doc, ["Dimensión", "Diversidad buscada"], [
        ("Especialización", "APOE, educación matemática, dominio matemático del caso y metodología de investigación."),
        ("Trayectoria", "Investigadores consolidados y personas con investigación doctoral o posdoctoral supervisada."),
        ("Contexto", "Distintas instituciones, niveles educativos y experiencias de formación, cuando sean pertinentes."),
        ("Posición respecto del tutor", "Personas vinculadas y no vinculadas al diseño, con registro transparente de la relación."),
    ], [1.45, 5.2])
    heading(doc, "Ficha breve de acreditación")
    para(doc, "Para cada persona invitada, registrar: código; formación y rol; evidencia concreta de conocimiento APOE; dominios matemáticos de experiencia; tres publicaciones, tesis o productos relevantes como máximo; vínculo con el Tutor APOE; y aceptación de las condiciones de uso de sus respuestas.")
    heading(doc, "Uso de los perfiles")
    para(doc, "El perfil no pretende certificar autoridad absoluta. Sirve para hacer visible por qué se convocó a cada integrante, qué alcance tiene su juicio y qué perspectivas conviene sumar antes de transformar el protocolo del tutor. Las respuestas se interpretan a la luz de esta información y no sólo por conteo de votos.")
    doc.save(OUT / "Perfil_panel_experto_APOE.docx")


def form():
    doc = base_doc("Ficha individual de juicio experto", "Instrumento de registro para la validación del Tutor APOE")
    para(doc, "Complete una ficha por cada ítem. Valore pertinencia, claridad y coherencia usando la escala 1 a 4. Al final de cada capa indique si el conjunto de tres ítems es suficiente y qué aspecto incorporaría, retiraría o reformularía.")
    heading(doc, "Identificación codificada")
    table(doc, ["Campo", "Registro"], [
        ("Código de especialista", "____________________________________________"),
        ("Fecha", "____________________________________________"),
        ("Dominio matemático desde el cual revisa", "____________________________________________"),
        ("Relación declarada con el Tutor APOE", "____________________________________________"),
    ], [2.45, 4.2])
    heading(doc, "Escala")
    para(doc, "1 = no cumple. 2 = requiere revisión mayor. 3 = requiere ajuste menor. 4 = cumple.")
    grouped = [("Capa 1 Conceptual", ITEMS[:3]), ("Capa 2 Operativa", ITEMS[3:6]), ("Capa 3 Contrastiva", ITEMS[6:9]), ("Capa 4 Genética", ITEMS[9:12])]
    for layer, entries in grouped:
        heading(doc, layer)
        for code, focus, statement, trace in entries:
            # Evita que el nombre de un item quede separado de su enunciado y tabla.
            if code in {"V03", "V11"}:
                doc.add_page_break()
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(3)
            r = p.add_run(f"{code}  {focus}")
            r.bold = True
            p.add_run(f"  |  Trazabilidad: {trace}")
            p = doc.add_paragraph(statement)
            p.paragraph_format.left_indent = Inches(0.12)
            p.paragraph_format.space_after = Pt(4)
            table(doc, ["Pertinencia", "Claridad", "Coherencia", "Justificación y propuesta de ajuste"], [
                ("1  2  3  4", "1  2  3  4", "1  2  3  4", "\n\n"),
            ], [0.92, 0.83, 0.95, 3.95], font_size=8.7)
        p = doc.add_paragraph()
        p.add_run("Suficiencia de la capa: ").bold = True
        p.add_run("1  2  3  4    Comentario o aspecto faltante: ________________________________________________")
        p.paragraph_format.space_after = Pt(12)
    heading(doc, "Síntesis final")
    table(doc, ["Pregunta", "Registro"], [
        ("¿Qué ítem debe revisarse con mayor prioridad?", "\n\n"),
        ("¿Qué reserva teórica desea conservar aunque no haya consenso?", "\n\n"),
        ("¿Qué fuente o argumento sustenta esa reserva?", "\n\n"),
    ], [2.6, 4.05])
    doc.save(OUT / "Ficha_individual_juicio_experto_APOE.docx")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    protocol()
    profile()
    form()
