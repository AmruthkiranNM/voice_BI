/* eslint-disable react-refresh/only-export-components */
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
    <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-5 sm:p-6">
      <h3 className="text-sm font-semibold text-white mb-4">Key numbers</h3>
      <div className={`grid gap-3 ${kpis.length === 1 ? 'grid-cols-1' : 'grid-cols-2'}`}>
        {kpis.map(kpi => (
          <div key={kpi.label} className="rounded-xl border border-white/8 bg-black/20 p-4 text-center">
            <p className="text-xs text-gray-500 mb-1 capitalize">{kpi.label}</p>
            <p className="text-2xl sm:text-3xl font-bold text-white tabular-nums">
              {formatKpiValue(kpi.value)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
