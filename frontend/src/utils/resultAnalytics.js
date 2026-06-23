/** Compute summary statistics from a query result for the results dashboard. */

export function analyzeResult(result) {
  if (!result?.rows?.length || !result?.columns?.length) return null;

  const { columns, rows } = result;
  const numericCols = columns.filter(col =>
    rows.some(r => {
      const v = r[col];
      return v != null && v !== '' && !Number.isNaN(Number(v));
    }),
  );

  const labelCol =
    columns.find(c => !numericCols.includes(c)) ||
    columns.find(c => rows.some(r => typeof r[c] === 'string' || isNaN(Number(r[c])))) ||
    columns[0];

  const numericStats = numericCols.map(col => {
    const values = rows.map(r => Number(r[col])).filter(v => !Number.isNaN(v));
    const sum = values.reduce((a, b) => a + b, 0);
    return {
      column: col,
      label: col.replace(/_/g, ' '),
      sum,
      avg: values.length ? sum / values.length : 0,
      min: values.length ? Math.min(...values) : 0,
      max: values.length ? Math.max(...values) : 0,
      count: values.length,
    };
  });

  let topEntry = null;
  if (labelCol && numericCols[0] && rows.length > 0) {
    const valueCol = numericCols[0];
    const sorted = [...rows].sort(
      (a, b) => Number(b[valueCol]) - Number(a[valueCol]),
    );
    const best = sorted[0];
    topEntry = {
      label: String(best[labelCol] ?? '—'),
      value: Number(best[valueCol]),
      valueColumn: valueCol.replace(/_/g, ' '),
    };
  }

  return {
    numericStats,
    labelCol,
    numericCols,
    rowCount: result.row_count ?? rows.length,
    columnCount: columns.length,
    topEntry,
  };
}

export function formatStatValue(value) {
  if (value == null || Number.isNaN(value)) return '—';
  if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (Math.abs(value) >= 1e4) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (Number.isInteger(value)) return value.toLocaleString();
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
