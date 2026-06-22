export default function ResultTable({ result }) {
  if (!result?.columns?.length || !result?.rows?.length) return null;

  const { columns, rows, row_count } = result;

  const fmt = (v) => {
    if (v == null) return '-';
    if (typeof v === 'number') return v.toLocaleString();
    return String(v);
  };

  const exportCsv = () => {
    const header = columns.join(',');
    const body = rows.map(row =>
      columns.map(c => {
        const val = row[c];
        const str = val == null ? '' : String(val);
        return str.includes(',') || str.includes('"') ? `"${str.replace(/"/g, '""')}"` : str;
      }).join(',')
    ).join('\n');
    const blob = new Blob([`${header}\n${body}`], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'business-analysis.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-5 sm:p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">Data</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={exportCsv}
            className="text-xs text-gray-500 hover:text-indigo-400 transition-colors"
          >
            Export CSV
          </button>
          <span className="text-xs text-gray-600">{row_count} rows</span>
        </div>
      </div>

      <div className="overflow-x-auto overflow-y-auto max-h-64 rounded-lg border border-white/5">
        <table className="w-full text-xs text-left">
          <thead className="text-[10px] font-bold text-gray-400 uppercase bg-[#0b0f19] sticky top-0 z-10 border-b border-white/5">
            <tr>
              {columns.map(c => (
                <th key={c} className="px-5 py-3 whitespace-nowrap">
                  {c.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {rows.map((row, i) => (
              <tr key={i} className="hover:bg-indigo-500/5 transition-colors">
                {columns.map(c => (
                  <td key={c} className="px-5 py-3 whitespace-nowrap text-gray-300 font-mono text-[11px]">
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
