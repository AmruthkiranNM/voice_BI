/** Schema + sample rows table for one table's preview data — no outer card, meant to sit inside a tab panel. */
export default function TablePreviewCard({ preview }) {
  if (!preview) return <p className="text-sm text-zinc-500">Loading preview…</p>;
  const { columns = [], preview_rows = [] } = preview;
  if (!preview_rows.length) return <p className="text-sm text-zinc-500">No rows to preview.</p>;

  return (
    <div className="overflow-x-auto max-h-64 scrollbar-thin rounded-xl border border-black/10">
      <table className="w-full text-xs text-left whitespace-nowrap">
        <thead className="sticky top-0 bg-card text-zinc-400 border-b border-black/10 z-10">
          <tr>
            {columns.map(col => (
              <th key={col} className="px-4 py-3 font-medium uppercase tracking-wider text-[10px]">
                {col.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-black/5 text-zinc-300">
          {preview_rows.slice(0, 8).map((row, i) => (
            <tr key={i} className="hover:bg-black/5 transition-colors">
              {columns.map(col => (
                <td key={col} className="px-4 py-2.5 truncate max-w-[200px]">
                  {row[col] ?? <span className="text-zinc-500">—</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
