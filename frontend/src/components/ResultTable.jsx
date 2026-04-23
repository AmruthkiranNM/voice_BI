/**
 * ResultTable — Data table with CSV export
 */
export default function ResultTable({ result }) {
  if (!result?.columns?.length || !result?.rows?.length) return null;

  const { columns, rows, row_count } = result;

  const exportCSV = () => {
    const header = columns.join(',');
    const body = rows.map(r =>
      columns.map(c => {
        const v = r[c];
        return typeof v === 'string' && v.includes(',') ? `"${v}"` : v ?? '';
      }).join(',')
    ).join('\n');
    const blob = new Blob([header + '\n' + body], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'results.csv';
    a.click();
  };

  const fmt = (v) => {
    if (v == null) return '—';
    if (typeof v === 'number') return v.toLocaleString();
    return String(v);
  };

  return (
    <div className="bg-card border border-border rounded-2xl p-6 fade-up-3
                    hover:border-border-hover transition-colors duration-200">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <span className="text-lg">📊</span>
          <h3 className="text-sm font-bold text-text-primary uppercase tracking-wide">
            Query Results
          </h3>
          <span className="px-2.5 py-0.5 rounded-md bg-green/10 text-green text-[11px] font-bold">
            {row_count} rows
          </span>
        </div>
        <button
          onClick={exportCSV}
          className="px-3.5 py-1.5 rounded-lg text-xs font-semibold
                     bg-bg border border-border text-text-muted
                     hover:text-green hover:border-green/30 transition-all duration-200"
        >
          ↓ Export CSV
        </button>
      </div>

      {/* Table */}
      <div className="overflow-auto rounded-xl border border-border max-h-[320px]">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-elevated">
            <tr>
              {columns.map(c => (
                <th key={c} className="px-4 py-3 text-left text-[11px] font-bold text-text-muted
                                     uppercase tracking-wider border-b border-border whitespace-nowrap">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-border/40 hover:bg-card-hover transition-colors">
                {columns.map(c => (
                  <td key={c} className="px-4 py-3 text-text-primary whitespace-nowrap
                                       font-mono text-[13px]">
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
