import { useMemo, useState, useRef, useCallback } from 'react';
import { TbSearch, TbX, TbChevronDown, TbChevronRight, TbDownload } from 'react-icons/tb';

const PAGE_SIZE = 25;

export default function ResultTable({ result, fullWidth = false }) {
  const [sort, setSort] = useState({ column: null, dir: 'asc' });
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(1);
  const [hiddenCols, setHiddenCols] = useState(new Set());
  const [pinnedCol, setPinnedCol] = useState(null);
  const [colWidths, setColWidths] = useState({});
  const [highlightRow, setHighlightRow] = useState(null);
  const [isExpanded, setIsExpanded] = useState(true);
  const resizingCol = useRef(null);
  const resizeStartX = useRef(0);
  const resizeStartW = useRef(0);

  const columns = result?.columns ?? [];
  const rows = result?.rows ?? [];

  const numericCols = useMemo(() =>
    columns.filter(c => rows.some(r => r[c] != null && !Number.isNaN(Number(r[c])))),
    [columns, rows],
  );

  const colType = (c) => {
    if (numericCols.includes(c)) return 'numeric';
    if (rows.some(r => /^\d{4}[-/]/.test(String(r[c] ?? '')))) return 'date';
    return 'text';
  };

  const colTypeIcon = (c) => {
    switch (colType(c)) {
      case 'numeric': return '#';
      case 'date': return '📅';
      default: return 'Aa';
    }
  };

  const visibleCols = useMemo(() => {
    const all = columns.filter(c => !hiddenCols.has(c));
    if (pinnedCol && all.includes(pinnedCol)) {
      return [pinnedCol, ...all.filter(c => c !== pinnedCol)];
    }
    return all;
  }, [columns, hiddenCols, pinnedCol]);

  const filteredRows = useMemo(() => {
    let out = rows;
    if (filter.trim()) {
      const needle = filter.trim().toLowerCase();
      out = out.filter(row => columns.some(c => String(row[c] ?? '').toLowerCase().includes(needle)));
    }
    if (sort.column) {
      const { column, dir } = sort;
      out = [...out].sort((a, b) => {
        const av = a[column]; const bv = b[column];
        const an = Number(av); const bn = Number(bv);
        let cmp = (!Number.isNaN(an) && !Number.isNaN(bn) && av !== '' && bv !== '') ? an - bn : String(av ?? '').localeCompare(String(bv ?? ''));
        return dir === 'asc' ? cmp : -cmp;
      });
    }
    return out;
  }, [rows, columns, filter, sort]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  const pagedRows = filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // Column totals
  const totals = useMemo(() => {
    const t = {};
    for (const c of numericCols) {
      t[c] = filteredRows.reduce((s, r) => s + (Number(r[c]) || 0), 0);
    }
    return t;
  }, [filteredRows, numericCols]);

  const fmt = (v, c) => {
    if (v == null) return <span className="text-zinc-500">—</span>;
    if (numericCols.includes(c)) {
      const n = Number(v);
      if (!Number.isNaN(n)) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    const s = String(v);
    if (filter && s.toLowerCase().includes(filter.toLowerCase())) {
      const idx = s.toLowerCase().indexOf(filter.toLowerCase());
      return (
        <span>
          {s.slice(0, idx)}
          <mark className="bg-[#9C4A2A]/30 text-zinc-100 rounded">{s.slice(idx, idx + filter.length)}</mark>
          {s.slice(idx + filter.length)}
        </span>
      );
    }
    return s;
  };

  const fmtTotal = (c) => {
    if (!numericCols.includes(c)) return '';
    const v = totals[c];
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
    if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  };

  const toggleSort = (col) => {
    setSort(prev => {
      if (prev.column !== col) return { column: col, dir: 'desc' };
      if (prev.dir === 'desc') return { column: col, dir: 'asc' };
      return { column: null, dir: 'asc' };
    });
    setPage(1);
  };

  const exportCsv = () => {
    const header = visibleCols.join(',');
    const body = filteredRows.map(row => visibleCols.map(c => {
      const val = row[c]; const str = val == null ? '' : String(val);
      return str.includes(',') || str.includes('"') ? `"${str.replace(/"/g, '""')}"` : str;
    }).join(',')).join('\n');
    const blob = new Blob([`${header}\n${body}`], { type: 'text/csv' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = 'data-export.csv'; a.click(); URL.revokeObjectURL(a.href);
  };

  const exportJson = () => {
    const data = filteredRows.map(row => Object.fromEntries(visibleCols.map(c => [c, row[c]])));
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = 'data-export.json'; a.click(); URL.revokeObjectURL(a.href);
  };

  // Column resize handlers
  const startResize = useCallback((e, col) => {
    resizingCol.current = col;
    resizeStartX.current = e.clientX;
    resizeStartW.current = colWidths[col] || 120;
    const onMove = (me) => {
      const delta = me.clientX - resizeStartX.current;
      setColWidths(prev => ({ ...prev, [resizingCol.current]: Math.max(60, resizeStartW.current + delta) }));
    };
    const onUp = () => { resizingCol.current = null; document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, [colWidths]);

  if (!columns.length || !rows.length) {
    return (
      <div className="bi-table-panel">
        <div className="bi-empty-state">
          <div className="bi-empty-icon">📭</div>
          <div className="bi-empty-title">No rows returned</div>
          <div className="bi-empty-sub">This query ran successfully but matched no data. Try a broader question or a different filter.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="bi-table-panel">
      {/* Table Header */}
      <div className="bi-table-header">
        <div className="flex items-center gap-2">
          <button className="bi-table-toggle" onClick={() => setIsExpanded(v => !v)} aria-label={isExpanded ? 'Collapse table' : 'Expand table'}>
            {isExpanded ? <TbChevronDown className="w-4 h-4" /> : <TbChevronRight className="w-4 h-4" />}
          </button>
          <h3 className="bi-table-title">Results</h3>
          <span className="bi-table-count">{filteredRows.length.toLocaleString()} rows · {visibleCols.length} cols</span>
        </div>

        <div className="bi-table-controls">
          {/* Search */}
          <div className="bi-search-wrap">
            <TbSearch className="bi-search-icon w-3.5 h-3.5" />
            <input
              type="text"
              value={filter}
              onChange={e => { setFilter(e.target.value); setPage(1); }}
              placeholder="Search rows…"
              className="bi-search-input"
            />
            {filter && (
              <button className="bi-search-clear" onClick={() => setFilter('')} aria-label="Clear search">
                <TbX className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Column visibility */}
          <div className="relative group">
            <button className="bi-ctrl-btn flex items-center gap-1">Columns <TbChevronDown className="w-3.5 h-3.5" /></button>
            <div className="bi-col-dropdown">
              {columns.map(c => (
                <label key={c} className="bi-col-item">
                  <input
                    type="checkbox"
                    checked={!hiddenCols.has(c)}
                    onChange={() => setHiddenCols(prev => {
                      const next = new Set(prev);
                      next.has(c) ? next.delete(c) : next.add(c);
                      return next;
                    })}
                    className="mr-2"
                  />
                  <span className="bi-col-type-icon">{colTypeIcon(c)}</span>
                  {c.replace(/_/g, ' ')}
                </label>
              ))}
            </div>
          </div>

          <button className="bi-ctrl-btn flex items-center gap-1" onClick={exportCsv}><TbDownload className="w-3.5 h-3.5" /> CSV</button>
          <button className="bi-ctrl-btn flex items-center gap-1" onClick={exportJson}><TbDownload className="w-3.5 h-3.5" /> JSON</button>
        </div>
      </div>

      {isExpanded && (
        <>
          <div className={`bi-table-wrap ${fullWidth ? 'max-h-[520px]' : 'max-h-72'}`}>
            <table className="bi-table">
              <thead className="bi-thead">
                <tr>
                  <th className="bi-th bi-th-rank">#</th>
                  {visibleCols.map(c => (
                    <th
                      key={c}
                      className={`bi-th ${sort.column === c ? 'sorted' : ''} ${pinnedCol === c ? 'pinned' : ''}`}
                      style={{ minWidth: colWidths[c] || 100, maxWidth: colWidths[c] || 240 }}
                      onClick={() => toggleSort(c)}
                    >
                      <div className="bi-th-inner">
                        <span className="bi-col-type-icon">{colTypeIcon(c)}</span>
                        <span className="bi-th-label">{c.replace(/_/g, ' ')}</span>
                        {sort.column === c && (
                          <span className="bi-sort-arrow">{sort.dir === 'asc' ? '↑' : '↓'}</span>
                        )}
                      </div>
                      {/* Resize handle */}
                      <div
                        className="bi-resize-handle"
                        onMouseDown={e => { e.stopPropagation(); startResize(e, c); }}
                      />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="bi-tbody">
                {pagedRows.map((row, i) => {
                  const globalRank = (page - 1) * PAGE_SIZE + i + 1;
                  return (
                    <tr
                      key={i}
                      className={`bi-tr ${highlightRow === i ? 'highlighted' : ''}`}
                      onMouseEnter={() => setHighlightRow(i)}
                      onMouseLeave={() => setHighlightRow(null)}
                    >
                      <td className="bi-td bi-td-rank">
                        <span className="bi-rank-badge">{globalRank}</span>
                      </td>
                      {visibleCols.map(c => (
                        <td
                          key={c}
                          className={`bi-td ${numericCols.includes(c) ? 'numeric' : ''} ${pinnedCol === c ? 'pinned' : ''}`}
                          title={String(row[c] ?? '')}
                          onDoubleClick={() => setPinnedCol(prev => prev === c ? null : c)}
                        >
                          {fmt(row[c], c)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
              {/* Totals row */}
              {filteredRows.length > 1 && (
                <tfoot className="bi-tfoot">
                  <tr>
                    <td className="bi-td bi-td-rank bi-total-label">Σ</td>
                    {visibleCols.map(c => (
                      <td key={c} className={`bi-td bi-total ${numericCols.includes(c) ? 'numeric highlight' : ''}`}>
                        {fmtTotal(c)}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="bi-pagination">
              <button className="bi-page-btn" onClick={() => setPage(1)} disabled={page === 1}>«</button>
              <button className="bi-page-btn" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>‹</button>
              <span className="bi-page-info">Page {page} of {totalPages} · {filteredRows.length.toLocaleString()} rows</span>
              <button className="bi-page-btn" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>›</button>
              <button className="bi-page-btn" onClick={() => setPage(totalPages)} disabled={page === totalPages}>»</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
