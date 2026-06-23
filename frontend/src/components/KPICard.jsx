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
    <div className="panel-card !rounded-sm">
      <h3 className="text-xs font-data uppercase tracking-wide text-gray-500 mb-4">Key numbers</h3>
      <div className={`grid gap-3 ${kpis.length === 1 ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4' : 'grid-cols-2 lg:grid-cols-4'}`}>
        {kpis.map(kpi => (
          <div key={kpi.label} className="border-l-2 border-[#c8ff4d]/60 bg-black/20 px-4 py-3">
            <p className="text-xs text-gray-500 mb-1 capitalize">{kpi.label}</p>
            <p className="text-2xl sm:text-3xl font-semibold text-white font-data">
              {formatKpiValue(kpi.value)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
