/**
 * SchemaPanel — RAG-retrieved database tables
 */
export default function SchemaPanel({ metadata }) {
  const tables = metadata?.tables_used || [];
  if (tables.length === 0) return null;

  return (
    <div className="bg-card border border-border rounded-2xl p-6 fade-up-1
                    hover:border-border-hover transition-colors duration-200">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <span className="text-lg">🔍</span>
          <h3 className="text-sm font-bold text-text-primary uppercase tracking-wide">
            RAG Schema
          </h3>
        </div>
        <span className="text-[11px] text-text-muted font-medium">
          {tables.length} tables found
        </span>
      </div>

      {/* Table List */}
      <div className="space-y-2.5">
        {tables.map((table) => (
          <div key={table}
            className="flex items-center gap-3 py-3 px-4 rounded-xl bg-bg/60 border border-border/40
                       hover:border-indigo/20 transition-colors duration-200">
            <span className="text-indigo-light text-xs">⬡</span>
            <span className="text-sm font-mono font-semibold text-text-primary">{table}</span>
          </div>
        ))}
      </div>

      <p className="mt-4 text-[10px] text-text-muted text-right italic">
        Retrieved via FAISS + sentence-transformers
      </p>
    </div>
  );
}
