/** CodeMirror 6 mínimo: edita texto fuente tal cual, sin re-serializar nada. */
import { useEffect, useRef } from "react";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { defaultHighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorState, type Extension } from "@codemirror/state";
import { EditorView, keymap, placeholder as placeholderExt } from "@codemirror/view";

export interface CodeEditorProps {
  initial: string;
  language?: "markdown" | "plain";
  placeholder?: string;
  onSave(text: string): void;
  onCancel(): void;
}

export function CodeEditor({ initial, language = "markdown", placeholder, onSave, onCancel }: CodeEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const handlers = useRef({ onSave, onCancel });
  handlers.current = { onSave, onCancel };

  useEffect(() => {
    if (!host.current) return;
    const commands = keymap.of([
      { key: "Mod-Enter", run: (view) => (handlers.current.onSave(view.state.doc.toString()), true) },
      { key: "Escape", run: () => (handlers.current.onCancel(), true) },
    ]);
    const extensions: Extension[] = [
      commands,
      history(),
      keymap.of([...defaultKeymap, ...historyKeymap]),
      EditorView.lineWrapping,
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
    ];
    if (language === "markdown") extensions.push(markdown());
    if (placeholder) extensions.push(placeholderExt(placeholder));
    const view = new EditorView({ state: EditorState.create({ doc: initial, extensions }), parent: host.current });
    viewRef.current = view;
    view.focus();
    return () => {
      viewRef.current = null;
      view.destroy();
    };
    // El editor se crea una vez por apertura; `initial` no se re-sincroniza mientras se edita.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = () => onSave(viewRef.current?.state.doc.toString() ?? initial);

  return (
    <div className="code-editor">
      <div ref={host} className="code-editor__host" />
      <div className="code-editor__actions">
        <button type="button" className="btn btn--primary" onClick={save}>
          Guardar <kbd>⌘↵</kbd>
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancelar <kbd>Esc</kbd>
        </button>
      </div>
    </div>
  );
}
