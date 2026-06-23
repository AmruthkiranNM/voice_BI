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

const DATE_PATTERN = /^\d{4}[-/]\d{1,2}([-/]\d{1,2})?$|^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/i;

/** Find a column whose values look like dates, if any. */
export function detectDateColumn(columns, rows) {
  return columns.find(c => rows.some(r => DATE_PATTERN.test(String(r[c] ?? '')))) || null;
}

/**
 * Compare the first half of a time-ordered series against the second half
 * (or last point vs previous point when there are few rows) to produce a
 * "this period vs last period" delta for the headline numeric column.
 */
export function periodComparison(result) {
  if (!result?.rows?.length || !result?.columns?.length) return null;
  const { columns, rows } = result;
  const numericCols = columns.filter(c => rows.some(r => !Number.isNaN(Number(r[c])) && r[c] !== ''));
  const dateCol = detectDateColumn(columns, rows);
  if (!dateCol || !numericCols.length) return null;

  const valueCol = numericCols[0];
  const sorted = [...rows].sort((a, b) => String(a[dateCol]).localeCompare(String(b[dateCol])));
  if (sorted.length < 2) return null;

  let current, previous;
  if (sorted.length <= 4) {
    current = Number(sorted[sorted.length - 1][valueCol]) || 0;
    previous = Number(sorted[sorted.length - 2][valueCol]) || 0;
  } else {
    const mid = Math.floor(sorted.length / 2);
    const firstHalf = sorted.slice(0, mid);
    const secondHalf = sorted.slice(mid);
    const sum = arr => arr.reduce((a, r) => a + (Number(r[valueCol]) || 0), 0);
    previous = sum(firstHalf);
    current = sum(secondHalf);
  }

  const delta = current - previous;
  const pct = previous !== 0 ? (delta / Math.abs(previous)) * 100 : null;

  return {
    column: valueCol.replace(/_/g, ' '),
    current,
    previous,
    delta,
    pct,
    direction: delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat',
  };
}

/** Flag rows whose value for `col` is a statistical outlier (IQR method). */
export function detectOutliers(rows, labelCol, valueCol) {
  const values = rows.map(r => Number(r[valueCol])).filter(v => !Number.isNaN(v)).sort((a, b) => a - b);
  if (values.length < 4) return [];

  const q1 = values[Math.floor(values.length * 0.25)];
  const q3 = values[Math.floor(values.length * 0.75)];
  const iqr = q3 - q1;
  const lower = q1 - 1.5 * iqr;
  const upper = q3 + 1.5 * iqr;

  return rows
    .filter(r => {
      const v = Number(r[valueCol]);
      return !Number.isNaN(v) && (v < lower || v > upper);
    })
    .map(r => ({
      label: String(r[labelCol] ?? '—'),
      value: Number(r[valueCol]),
      type: Number(r[valueCol]) > upper ? 'high' : 'low',
    }));
}

/** Pearson correlation coefficient between two numeric columns, if both have a numeric column besides the label. */
export function correlation(rows, colA, colB) {
  const pairs = rows
    .map(r => [Number(r[colA]), Number(r[colB])])
    .filter(([a, b]) => !Number.isNaN(a) && !Number.isNaN(b));
  if (pairs.length < 4) return null;

  const n = pairs.length;
  const sumA = pairs.reduce((s, [a]) => s + a, 0);
  const sumB = pairs.reduce((s, [, b]) => s + b, 0);
  const meanA = sumA / n;
  const meanB = sumB / n;

  let num = 0, denomA = 0, denomB = 0;
  for (const [a, b] of pairs) {
    num += (a - meanA) * (b - meanB);
    denomA += (a - meanA) ** 2;
    denomB += (b - meanB) ** 2;
  }
  const denom = Math.sqrt(denomA * denomB);
  if (denom === 0) return null;

  return num / denom;
}

/** Simple moving average for a trendline overlay. */
export function movingAverage(values, window = 3) {
  return values.map((_, i) => {
    const start = Math.max(0, i - window + 1);
    const slice = values.slice(start, i + 1);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });
}

/** Running total of a series. */
export function cumulativeSum(values) {
  let running = 0;
  return values.map(v => (running += v));
}

/**
 * Build a list of plain-English callouts about the result — period change,
 * outliers, correlation — computed directly from the data (not the LLM),
 * so they're always accurate even on a small local model.
 */
export function buildCallouts(result) {
  if (!result?.rows?.length || !result?.columns?.length) return [];
  const { rows } = result;
  const analysis = analyzeResult(result);
  const callouts = [];

  const comparison = periodComparison(result);
  if (comparison && comparison.pct != null) {
    const pctStr = `${comparison.pct >= 0 ? '+' : ''}${comparison.pct.toFixed(1)}%`;
    callouts.push({
      type: comparison.direction === 'up' ? 'positive' : comparison.direction === 'down' ? 'negative' : 'neutral',
      text: `${comparison.column} is ${pctStr} compared to the earlier period in this result (${formatStatValue(comparison.previous)} → ${formatStatValue(comparison.current)}).`,
    });
  }

  if (analysis?.labelCol && analysis.numericCols[0]) {
    const outliers = detectOutliers(rows, analysis.labelCol, analysis.numericCols[0]).slice(0, 3);
    for (const o of outliers) {
      callouts.push({
        type: o.type === 'high' ? 'positive' : 'negative',
        text: `"${o.label}" stands out — its ${analysis.numericCols[0].replace(/_/g, ' ')} (${formatStatValue(o.value)}) is unusually ${o.type === 'high' ? 'high' : 'low'} compared to the rest of the results.`,
      });
    }
  }

  if (analysis?.numericCols?.length >= 2) {
    const r = correlation(rows, analysis.numericCols[0], analysis.numericCols[1]);
    if (r != null && Math.abs(r) >= 0.6) {
      const a = analysis.numericCols[0].replace(/_/g, ' ');
      const b = analysis.numericCols[1].replace(/_/g, ' ');
      callouts.push({
        type: 'neutral',
        text: `${a} and ${b} appear ${r > 0 ? 'positively' : 'negatively'} correlated across these results (r ≈ ${r.toFixed(2)}).`,
      });
    }
  }

  return callouts;
}
