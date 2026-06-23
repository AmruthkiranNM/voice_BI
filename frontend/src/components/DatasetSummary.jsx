export default function DatasetSummary({ datasetInfo }) {
  if (!datasetInfo?.has_data) return null;

  const domain = datasetInfo.domain || {};
  const businessType = domain.business_type || domain.label;
  const columns = datasetInfo.columns || domain.column_names || [];
  const numeric = domain.numeric_columns || [];
  const categories = domain.category_columns || [];
  const dates = domain.date_columns || [];

  return (
    <div className="panel-card h-full">
      <h3 className="text-xs font-data uppercase tracking-wide text-gray-500 mb-4">Your dataset</h3>

      <dl className="space-y-3 text-sm">
        {businessType && (
          <div>
            <dt className="text-gray-500 text-xs">Type</dt>
            <dd className="text-white font-medium mt-0.5">{businessType}</dd>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <dt className="text-gray-500 text-xs">Rows</dt>
            <dd className="text-white font-semibold mt-0.5 font-data">
              {datasetInfo.rowCount?.toLocaleString() ?? '—'}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500 text-xs">Columns</dt>
            <dd className="text-white font-semibold mt-0.5 font-data">
              {columns.length || '—'}
            </dd>
          </div>
        </div>
        {datasetInfo.tableName && (
          <div>
            <dt className="text-gray-500 text-xs">Source</dt>
            <dd className="text-gray-300 mt-0.5 capitalize truncate">
              {datasetInfo.tableName.replace(/_/g, ' ')}
            </dd>
          </div>
        )}
      </dl>

      {(numeric.length > 0 || categories.length > 0 || dates.length > 0) && (
        <div className="mt-5 pt-4 border-t border-white/5 space-y-3">
          {numeric.length > 0 && (
            <ColumnGroup label="Numbers" items={numeric} color="text-emerald-400" />
          )}
          {categories.length > 0 && (
            <ColumnGroup label="Groups" items={categories.slice(0, 6)} color="text-[#c8ff4d]" extra={categories.length - 6} />
          )}
          {dates.length > 0 && (
            <ColumnGroup label="Dates" items={dates} color="text-amber-400" />
          )}
        </div>
      )}
    </div>
  );
}

function ColumnGroup({ label, items, color, extra }) {
  return (
    <div>
      <p className="text-xs text-gray-500 mb-1.5">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {items.map(col => (
          <span
            key={col}
            className={`text-[11px] px-2 py-0.5 bg-white/5 border border-white/10 font-data ${color}`}
          >
            {col.replace(/_/g, ' ')}
          </span>
        ))}
        {extra > 0 && (
          <span className="text-[11px] text-gray-600 px-1">+{extra} more</span>
        )}
      </div>
    </div>
  );
}
