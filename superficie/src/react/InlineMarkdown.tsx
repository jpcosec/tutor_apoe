/** Formato inline mínimo para el texto literal del template: negrita, cursiva, código y links. */
import type { ReactNode } from "react";

const TOKEN = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*\*|_[^_\s][^_]*_|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;

function renderToken(token: string, key: number): ReactNode {
  if (/^(\*\*|__)/.test(token)) return <strong key={key}>{token.slice(2, -2)}</strong>;
  if (token.startsWith("`")) return <code key={key}>{token.slice(1, -1)}</code>;
  const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
  if (link) {
    return (
      <a key={key} href={link[2]} target="_blank" rel="noreferrer">
        {link[1]}
      </a>
    );
  }
  return <em key={key}>{token.slice(1, -1)}</em>;
}

export function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(TOKEN);
  return <>{parts.map((part, i) => (i % 2 === 1 ? renderToken(part, i) : part))}</>;
}
