export default function ResultTable({ result }) {
  if (!result?.columns?.length || !result?.rows?.length) return null;

  const { columns, rows, row_count } = result;

  const fmt = (v) => {
    if (v == null) return '-';
    if (typeof v === 'number') return v.toLocaleString();
    return String(v);
  };

  return (
    <div className="panel-card w-full">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-green-500/10 flex items-center justify-center text-green-400">📊</div>
          <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider">Database Results</h3>
        </div>
        <span className="px-3 py-1 rounded-md bg-green-500/10 text-green-400 border border-green-500/20 text-xs font-bold">
          {row_count} ROWS RETURNED
        </span>
      </div>

      <div className="overflow-x-auto overflow-y-auto max-h-[400px] border border-gray-800 rounded-xl w-full bg-gray-900/30">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-gray-400 uppercase bg-gray-800/80 sticky top-0 z-10 backdrop-blur-sm">
            <tr>
              {columns.map(c => (
                <th key={c} className="px-6 py-4 font-bold border-b border-gray-700 whitespace-nowrap">
                  {c.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {rows.map((row, i) => (
              <tr key={i} className="hover:bg-gray-800/40 transition-colors">
                {columns.map(c => (
                  <td key={c} className="px-6 py-3.5 whitespace-nowrap text-gray-200 font-mono text-[13px]">
                    {fmt(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
