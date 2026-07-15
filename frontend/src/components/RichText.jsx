/**
 * Minimal markdown-ish renderer for LLM answers: **bold**, numbered/bulleted
 * lists, and paragraphs, with numbers highlighted in the accent colour.
 * ponytail: handles the narrow subset the agents emit, not full markdown —
 * swap in react-markdown if richer formatting is ever needed.
 */
function highlightNumbers(text, key) {
  return text.split(/(\$?[\d,]+\.?\d*%?)/g).map((p, i) =>
    /^\$?[\d,]+\.?\d*%?$/.test(p) && p.trim()
      ? <span key={`${key}-${i}`} className="font-data font-semibold text-[#3b82f6]">{p}</span>
      : p
  );
}

function inline(text, key) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    /^\*\*[^*]+\*\*$/.test(p)
      ? <strong key={`${key}-${i}`} className="text-white font-semibold">{p.slice(2, -2)}</strong>
      : highlightNumbers(p, `${key}-${i}`)
  );
}

export default function RichText({ text, className = '' }) {
  if (!text) return null;

  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const blocks = [];
  let list = null;
  for (const line of lines) {
    const m = line.match(/^(?:(\d+)\.|[-*])\s+(.*)/);
    if (m) {
      const ordered = m[1] !== undefined;
      if (list && list.ordered !== ordered) { blocks.push(list); list = null; }
      (list ||= { type: 'list', ordered, items: [] }).items.push(m[2]);
      continue;
    }
    if (list) { blocks.push(list); list = null; }
    blocks.push({ type: 'p', text: line });
  }
  if (list) blocks.push(list);

  return (
    <div className={`space-y-2 ${className}`}>
      {blocks.map((b, i) => {
        if (b.type !== 'list') return <p key={i} className="leading-relaxed">{inline(b.text, i)}</p>;
        const ListTag = b.ordered ? 'ol' : 'ul';
        return (
          <ListTag key={i} className={`${b.ordered ? 'list-decimal' : 'list-disc'} list-inside space-y-1`}>
            {b.items.map((it, j) => <li key={j}>{inline(it, `${i}-${j}`)}</li>)}
          </ListTag>
        );
      })}
    </div>
  );
}
