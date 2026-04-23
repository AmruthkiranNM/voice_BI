/**
 * SQLPanel — Displays generated SQL with copy button
 */
import { useState } from 'react';

export default function SQLPanel({ sql, warnings }) {
  const [copied, setCopied] = useState(false);

  if (!sql) return null;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // Format SQL with line breaks
  const formatted = sql
    .replace(/\b(SELECT|FROM|WHERE|JOIN|LEFT JOIN|INNER JOIN|GROUP BY|ORDER BY|HAVING|LIMIT|AND|OR|ON)\b/gi, '\n$1')
    .replace(/^\n/, '')
    .trim();

  return (
    <div className="bg-card border border-border rounded-2xl p-6 fade-up-2
                    hover:border-border-hover transition-colors duration-200">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <span className="text-lg">⚡</span>
          <h3 className="text-sm font-bold text-text-primary uppercase tracking-wide">
            Generated SQL
          </h3>
        </div>
        <button
          onClick={handleCopy}
          className="px-3.5 py-1.5 rounded-lg text-xs font-semibold
                     bg-bg border border-border text-text-muted
                     hover:text-indigo hover:border-indigo/30 transition-all duration-200"
        >
          {copied ? '✓ Copied!' : 'Copy'}
        </button>
      </div>

      {/* SQL Code Block */}
      <div className="bg-[#0a0e1a] border border-border rounded-xl p-5 overflow-x-auto">
        <pre className="text-[13px] leading-7 font-mono text-indigo-light whitespace-pre-wrap">
          <code>{formatted}</code>
        </pre>
      </div>

      {/* Warnings */}
      {warnings?.length > 0 && (
        <div className="mt-4 p-4 rounded-xl bg-amber/5 border border-amber/15">
          {warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber font-medium">⚠ {w}</p>
          ))}
        </div>
      )}
    </div>
  );
}
