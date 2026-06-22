/** Detect single-value KPI metrics from a query result. */
export function detectKpiMetrics(result) {
  if (!result?.rows?.length || !result?.columns?.length) return null;

  const { columns, rows } = result;

  if (rows.length === 1) {
    const kpis = columns
      .filter(c => rows[0][c] != null && !Number.isNaN(Number(rows[0][c])))
      .map(c => ({
        label: c.replace(/_/g, ' '),
        value: Number(rows[0][c]),
        raw: rows[0][c],
      }));
    if (kpis.length >= 1 && kpis.length <= 6) return kpis;
  }

  if (rows.length <= 3 && columns.length === 2) {
    const numericCol = columns.find(c => rows.every(r => !Number.isNaN(Number(r[c]))));
    const labelCol = columns.find(c => c !== numericCol);
    if (numericCol && labelCol && rows.length === 1) {
      return [{
        label: String(rows[0][labelCol]),
        value: Number(rows[0][numericCol]),
        raw: rows[0][numericCol],
      }];
    }
  }

  return null;
}

function formatKpiValue(value) {
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e4) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (Number.isInteger(value)) return value.toLocaleString();
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export default function KPICard({ result }) {
  const kpis = detectKpiMetrics(result);
  if (!kpis?.length) return null;

  return (
    <div className="panel-card w-full">
      <div className="flex items-center gap-3 mb-5">
        <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400">🎯</div>
        <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider">Key Metric</h3>
      </div>

      <div className={`grid gap-4 ${kpis.length === 1 ? 'grid-cols-1' : 'grid-cols-2 lg:grid-cols-3'}`}>
        {kpis.map(kpi => (
          <div
            key={kpi.label}
            className="rounded-2xl border border-indigo-500/20 bg-gradient-to-br from-indigo-950/40 to-gray-900/60 p-6 text-center"
          >
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">{kpi.label}</p>
            <p className="text-4xl font-extrabold text-indigo-300 tabular-nums">
              {formatKpiValue(kpi.value)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
