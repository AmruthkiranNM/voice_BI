import { useEffect, useState } from 'react';
import { TbFileSpreadsheet } from 'react-icons/tb';

/**
 * One card with a tab strip across the top — pick a table, see its content
 * below — instead of stacking every table's card one after another.
 */
export default function TabbedTables({ tableNames, previews, renderTable }) {
  const [active, setActive] = useState(tableNames[0] || null);

  // Keep the active tab valid if the table list changes (e.g. switching
  // data source, or a table gets removed).
  useEffect(() => {
    if (!tableNames.includes(active)) setActive(tableNames[0] || null);
  }, [tableNames, active]);

  if (!tableNames.length) return null;

  return (
    <div className="surface-card overflow-hidden animate-in">
      <div className="flex items-center gap-1 p-1.5 overflow-x-auto scrollbar-none border-b border-black/10">
        {tableNames.map(name => (
          <button
            key={name}
            type="button"
            onClick={() => setActive(name)}
            className={`flex items-center gap-1.5 shrink-0 text-xs font-medium px-3.5 py-2 rounded-full transition-colors whitespace-nowrap ${
              active === name ? 'active-pill' : 'text-zinc-400 hover:text-zinc-100 hover:bg-black/5'
            }`}
          >
            <TbFileSpreadsheet className="w-3.5 h-3.5" />
            {name.replace(/_/g, ' ')}
            {previews[name]?.row_count != null && (
              <span className="text-[10px] text-zinc-500">{previews[name].row_count.toLocaleString()}</span>
            )}
          </button>
        ))}
      </div>
      <div className="p-6">
        {renderTable(active, previews[active])}
      </div>
    </div>
  );
}
