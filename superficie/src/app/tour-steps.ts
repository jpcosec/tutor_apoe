import type { WorkbenchViewId } from "./workbench-router";
import type { WorkbenchLens } from "../workbench/ProsaWorkbenchView";

/** Un paso del recorrido: qué elemento señala, qué dice y a qué vista hay que ir para verlo. */
export interface TourStep {
  id: string;
  title: string;
  body: string[];
  /** Selector CSS del elemento que se señala; sin él, el paso va centrado. */
  target?: string;
  view?: WorkbenchViewId;
  lens?: WorkbenchLens;
}

export const TOUR_STEPS: TourStep[] = [
  {
    id: "inicio",
    title: "Qué es esto",
    body: [
      "El Workbench es la interfaz de un store SLDB: muestra sus documentos como prosa y deja trabajarlos sin abrir archivos.",
      "Lo que ves sale del sldb serve al que está conectado. Este recorrido usa el documento que tengas abierto.",
    ],
  },
  {
    id: "documento",
    title: "Qué documento estás viendo",
    body: [
      "La ruta de la cabecera dice el modelo y el identificador del documento abierto.",
      "Haz clic en el nombre, o pulsa ⌘K, para buscar otro documento o un modelo y abrirlo.",
    ],
    target: '[data-testid="breadcrumb-doc-switch"]',
    view: "workbench",
  },
  {
    id: "lentes",
    title: "Tres lentes sobre la misma página",
    body: [
      "Lectura deja solo la prosa. Estructura / Fierros agrega en el margen qué es cada bloque y con qué operación se guarda. Esquema abre el contrato del modelo.",
      "También con las teclas 1, 2 y 3.",
    ],
    target: ".wb-lens-nav",
    view: "workbench",
  },
  {
    id: "arbol",
    title: "El documento y sus piezas",
    body: [
      "A la izquierda está el documento como raíz y, hacia la derecha, las piezas que compone o referencia: átomos, diagramas y su fuente.",
      "Un clic en una pieza la abre: un documento va a la prosa, un diagrama al inspector y una fuente a la vista de anclaje.",
    ],
    target: '[data-testid="topology-mindmap"]',
    view: "workbench",
  },
  {
    id: "editar",
    title: "Leer y editar en el lugar",
    body: [
      "La columna derecha es el documento. Haz clic en un campo editable para escribir; Ctrl o ⌘ + Enter guarda y Esc cancela.",
      "Guardar envía POST /save a SLDB con la versión que leíste; si el documento cambió entretanto, SLDB lo rechaza y la página lo avisa.",
      "Una pieza transcluida se edita ahí mismo y el cambio se escribe en su documento de origen.",
    ],
    target: '[data-testid="prosa-workbench-view"] .wb-editorial-sheet',
    view: "workbench",
    lens: "fierros",
  },
  {
    id: "diagramas",
    title: "Diagramas",
    body: [
      "Esta vista dibuja un diagrama del store. Un clic en un nodo lo selecciona y abre su ficha a la derecha: los átomos que lo justifican y sus referencias.",
      "Se llega desde un bloque de diagrama en la prosa o desde ⌘K.",
    ],
    target: '[data-testid="spec2viz-inspector-view"]',
    view: "diagram",
  },
  {
    id: "anclaje",
    title: "Fuente y anclaje",
    body: [
      "Aquí se lee un texto fuente y se extraen átomos de él. Selecciona un tramo: aparece un recuadro con su posición, un nombre sugerido y si ya existe algo parecido en el store.",
      "Crear AtomDoc y Anclar registra el átomo nuevo.",
    ],
    target: '[data-testid="source-anchoring-view"]',
    view: "source",
  },
  {
    id: "modelos",
    title: "Model Studio",
    body: [
      "El contrato de un modelo: sus campos y su plantilla. En un borrador puedes agregar o quitar campos y editar la plantilla.",
      "Validar muestra a cuántos documentos afecta el cambio; Promover lo aplica. Los modelos propios de sldb y de deskops son de solo lectura.",
    ],
    target: '[data-testid="model-studio-view"]',
    view: "studio",
  },
  {
    id: "asistente",
    title: "Asistente",
    body: [
      "Abre un chat que sabe qué documento y qué vista tienes en pantalla. Puedes pedirle que lea, busque o edite.",
      "Trabaja solo con las operaciones de SLDB (por MCP) y muestra cada una que usa. Si escribe algo, la página se recarga con el resultado.",
    ],
    target: '[data-testid="assist-open-assistant"]',
  },
  {
    id: "fin",
    title: "Listo",
    body: ["Puedes repetir este recorrido cuando quieras con el botón Recorrido, abajo a la derecha."],
    target: '[data-testid="assist-open-tour"]',
  },
];
