import { isCodeColumn } from './semanticClassifier';

// Phrasings the planner reliably understands, filled in with the active
// source's real column names so typed questions land on a known-good shape.
const NUMERIC = /int|real|float|double|numeric|decimal|money|number/i;
const DATE = /date|time/i;
const DATE_NAME = /(^|_)(date|time|timestamp|month|year|day|created|ordered|invoice_?date)(_|$)|_at$/i;
const human = s => String(s).replace(/_/g, ' ').trim();

export function buildQueryTemplates(tables = []) {
  const out = new Set();
  for (const t of tables) {
    const cols = t.columns || [];
    const measures = cols.filter(c => NUMERIC.test(c.type) && !isCodeColumn(c.name) && !DATE_NAME.test(c.name)).map(c => human(c.name));
    const dims = cols.filter(c => !NUMERIC.test(c.type) && !DATE.test(c.type) && !DATE_NAME.test(c.name) && !isCodeColumn(c.name)).map(c => human(c.name));
    const hasDate = cols.some(c => DATE.test(c.type) || DATE_NAME.test(c.name));
    const table = human(t.name);

    out.add(`Show details of every ${table}`);
    for (const m of measures.slice(0, 4)) {
      out.add(`Total ${m}`);
      if (hasDate) {
        out.add(`Show monthly ${m} trend`);
        out.add(`Forecast ${m} for the next 12 months`);
      }
      for (const d of dims.slice(0, 4)) {
        out.add(`Total ${m} by ${d}`);
        out.add(`Top 10 ${d} by ${m}`);
        out.add(`Average ${m} by ${d}`);
        if (hasDate) out.add(`Forecast ${m} by ${d} for the next 12 months`);
      }
    }
  }
  return [...out];
}

const STOP = new Set(['the', 'a', 'an', 'of', 'for', 'by', 'in', 'on', 'to', 'is', 'are', 'what', 'which', 'show', 'me', 'my', 'and', 'with', 'how', 'much', 'many', 'give', 'can', 'you', 'all', 'per', 'each', 'every']);

// Rank templates by how many of the typed words they contain (prefix match
// either way, so "countries" ~ "country" and "rev" ~ "revenue").
export function matchTemplates(templates, input, limit = 6) {
  const words = input.toLowerCase().split(/[^a-z0-9]+/).filter(w => w.length > 1 && !STOP.has(w));
  if (!words.length) return [];
  const hit = (w, tw) => tw.startsWith(w) || (w.length > 3 && w.startsWith(tw.slice(0, -1)) && tw.length > 3);
  return templates
    .map(t => {
      const tw = t.toLowerCase().split(/\s+/);
      return { t, score: words.filter(w => tw.some(x => hit(w, x))).length };
    })
    .filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score || a.t.length - b.t.length)
    .slice(0, limit)
    .map(x => x.t)
    .filter(t => t.toLowerCase() !== input.trim().toLowerCase());
}
