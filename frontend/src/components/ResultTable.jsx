import { useMemo, useState } from 'react';

export default function ResultTable({ result, fullWidth = false }) {
  const [sort, setSort] = useState({ column: null, dir: 'asc' });
  const [filter, setFilter] = useState('');

  const columns = result?.columns ?? [];
  const rows = result?.rows ?? [];

  const visibleRows = useMemo(() => {
    let out = rows;

    if (filter.trim()) {
      const needle = filter.trim().toLowerCase();
      out = out.filter(row =>
        columns.some(c => String(row[c] ?? '').toLowerCase().includes(needle)),
      );
    }

    if (sort.column) {
      const { column, dir } = sort;
      out = [...out].sort((a, b) => {
        const av = a[column];
        const bv = b[column];
        const an = Number(av);
        const bn = Number(bv);
        let cmp;
        if (!Number.isNaN(an) && !Number.isNaN(bn) && av !== '' && bv !== '') {
          cmp = an - bn;
        } else {
          cmp = String(av ?? '').localeCompare(String(bv ?? ''));
        }
        return dir === 'asc' ? cmp : -cmp;
      });
    }

    return out;
  }, [rows, columns, filter, sort]);

  if (!columns.length || !rows.length) return null;

  const fmt = (v) => {
    if (v == null) return '-';
    if (typeof v === 'number') return v.toLocaleString();
    return String(v);
  };

  const toggleSort = (col) => {
    setSort(prev => {
      if (prev.column !== col) return { column: col, dir: 'asc' };
      if (prev.dir === 'asc') return { column: col, dir: 'desc' };
      return { column: null, dir: 'asc' };
    });
  };

  const exportCsv = () => {
    const header = columns.join(',');
    const body = visibleRows.map(row =>
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
    <div className="panel-card">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <h3 className="text-xs font-data uppercase tracking-wide text-gray-500">Data</h3>
        <div className="flex items-center gap-3 font-data">
          <input
            type="text"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter rows…"
            className="bg-white/[0.03] border border-white/10 px-2.5 py-1.5 text-xs text-white placeholder:text-gray-600 outline-none focus:border-[#c8ff4d]/50 transition-colors w-32 sm:w-44"
          />
          <button
            onClick={exportCsv}
            className="text-xs text-gray-500 hover:text-[#c8ff4d] transition-colors whitespace-nowrap"
          >
            Export CSV
          </button>
          <span className="text-xs text-gray-600 whitespace-nowrap">
            {visibleRows.length}{visibleRows.length !== rows.length ? ` / ${rows.length}` : ''} rows
          </span>
        </div>
      </div>

      <div className={`overflow-x-auto overflow-y-auto border border-white/10 ${
        fullWidth ? 'max-h-[480px]' : 'max-h-64'
      }`}>
        <table className="w-full text-xs text-left">
          <thead className="text-[10px] font-bold text-gray-400 uppercase bg-[#121210] sticky top-0 z-10 border-b border-white/10">
            <tr>
              {columns.map(c => (
                <th
                  key={c}
                  onClick={() => toggleSort(c)}
                  className="px-5 py-3 whitespace-nowrap cursor-pointer select-none hover:text-white transition-colors"
                >
                  {c.replace(/_/g, ' ')}
                  {sort.column === c && (sort.dir === 'asc' ? ' ↑' : ' ↓')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {visibleRows.map((row, i) => (
              <tr key={i} className="hover:bg-[#c8ff4d]/5 transition-colors">
                {columns.map(c => (
                  <td key={c} className="px-5 py-3 whitespace-nowrap text-gray-300 font-data text-[11px]">
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
