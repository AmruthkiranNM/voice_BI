export default function SchemaPanel({ metadata }) {
  const tables = metadata?.tables_used || [];
  if (tables.length === 0) return null;

  return (
    <div className="panel-card w-full">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-cyan-500/10 flex items-center justify-center text-cyan-400">🔍</div>
          <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider">Retrieved Schema</h3>
        </div>
        <span className="px-3 py-1 rounded-md bg-gray-800 text-gray-400 border border-gray-700 text-xs font-bold uppercase">
          {tables.length} TABLES
        </span>
      </div>

      <div className="flex flex-wrap gap-3 mt-2">
        {tables.map((table) => (
          <div key={table} className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-gray-900 border border-gray-800">
            <span className="text-cyan-500 text-sm">⬡</span>
            <span className="text-sm font-mono font-bold text-gray-300">{table}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
