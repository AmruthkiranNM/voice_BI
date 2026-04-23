import { useState } from 'react';

export default function SQLPanel({ sql, warnings }) {
  const [copied, setCopied] = useState(false);

  if (!sql) return null;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatted = sql
    .replace(/\b(SELECT|FROM|WHERE|JOIN|LEFT JOIN|INNER JOIN|GROUP BY|ORDER BY|LIMIT)\b/gi, '\n$1')
    .replace(/^\n/, '').trim();

  return (
    <div className="panel-card w-full">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center text-blue-400">⚡</div>
          <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider">Generated SQL Query</h3>
        </div>
        <button
          onClick={handleCopy}
          className="px-4 py-1.5 rounded-lg text-xs font-bold bg-gray-800 border border-gray-700 text-gray-300 hover:text-white hover:bg-gray-700 transition-colors"
        >
          {copied ? '✓ COPIED' : 'COPY SQL'}
        </button>
      </div>

      <div className="bg-[#050914] border border-gray-800 rounded-xl p-5 overflow-x-auto w-full">
        <pre className="text-[13px] leading-relaxed font-mono text-blue-300">
          <code>{formatted}</code>
        </pre>
      </div>

      {warnings?.length > 0 && (
        <div className="mt-4 p-4 rounded-xl bg-red-500/10 border border-red-500/20 flex flex-col gap-2">
          {warnings.map((w, i) => (
            <div key={i} className="flex gap-2 text-sm text-red-400">
              <span>⚠️</span>
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
