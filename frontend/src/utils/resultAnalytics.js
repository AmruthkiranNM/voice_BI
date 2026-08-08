import { resolveVisualizationSpec } from './semanticClassifier';

/** Compute summary statistics from a query result for the results dashboard. */
export function analyzeResult(result, intent = '', query = '') {
  if (!result?.rows?.length || !result?.columns?.length) return null;

  const spec = resolveVisualizationSpec(result, intent, query);
  const { columns, rows } = result;
  
  // Filter out non-numeric columns, and strictly exclude identifiers based on spec
  let numericCols = columns.filter(col =>
    rows.some(r => {
      const v = r[col];
      return v != null && v !== '' && !Number.isNaN(Number(v));
    }),
  );

  if (spec && spec.excludedFields) {
    numericCols = numericCols.filter(c => !spec.excludedFields.includes(c));
  }

  // Use the semantic dimension as the label column, or fallback
  const labelCol = spec?.dimension || columns[0];

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
  if (labelCol && numericCols.length > 0 && rows.length > 0) {
    const valueCol = spec?.primaryMeasure || numericCols[0];
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
 * Project future values with an ordinary least-squares linear trend fit on
 * the series index. Clamped at 0 since business metrics are non-negative.
 * Returns the slope/intercept too so callers can describe the trend.
 */
export function linearForecast(values, periods = 3) {
  const n = values.length;
  if (n < 2) return { forecast: [], slope: 0, intercept: values[0] ?? 0 };

  const meanX = (n - 1) / 2;
  const meanY = values.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (i - meanX) * (values[i] - meanY);
    den += (i - meanX) ** 2;
  }
  const slope = den === 0 ? 0 : num / den;
  const intercept = meanY - slope * meanX;

  const forecast = [];
  for (let k = 1; k <= periods; k++) {
    forecast.push(Math.max(0, intercept + slope * (n - 1 + k)));
  }
  return { forecast, slope, intercept };
}

/**
 * Generate labels for the projected periods. Understands YYYY-MM (increments
 * the month) and plain integers; otherwise falls back to "+1, +2, …".
 */
export function nextLabels(labels, periods = 3) {
  const last = String(labels[labels.length - 1] ?? '');

  const month = last.match(/^(\d{4})-(\d{1,2})$/);
  if (month) {
    let year = Number(month[1]);
    let mon = Number(month[2]);
    const out = [];
    for (let k = 0; k < periods; k++) {
      mon += 1;
      if (mon > 12) { mon = 1; year += 1; }
      out.push(`${year}-${String(mon).padStart(2, '0')}`);
    }
    return out;
  }

  if (/^\d+$/.test(last)) {
    const base = Number(last);
    return Array.from({ length: periods }, (_, k) => String(base + k + 1));
  }

  return Array.from({ length: periods }, (_, k) => `+${k + 1}`);
}

/**
 * Project a declining numeric time series forward to the period where it
 * crosses zero (using the same least-squares trend as linearForecast).
 * Turns "here's a trend line" into an actionable statement — "at this rate,
 * you'll run out / hit zero in ~N periods" — without requiring the user to
 * define a target threshold. Only surfaces for a real decline within a
 * plausible horizon; a flat or growing trend, or a projection decades out,
 * isn't useful to say out loud.
 */
export function thresholdProjection(result) {
  if (!result?.rows?.length || !result?.columns?.length) return null;
  const { columns, rows } = result;
  const dateCol = detectDateColumn(columns, rows);
  if (!dateCol) return null;

  const numericCols = columns.filter(c => c !== dateCol && rows.some(r => !Number.isNaN(Number(r[c])) && r[c] !== ''));
  if (!numericCols.length) return null;
  const valueCol = numericCols[0];

  const sorted = [...rows].sort((a, b) => String(a[dateCol]).localeCompare(String(b[dateCol])));
  const values = sorted.map(r => Number(r[valueCol]) || 0);
  if (values.length < 4) return null;

  const { slope, intercept } = linearForecast(values, 1);
  const lastValue = values[values.length - 1];
  if (slope >= 0 || lastValue <= 0) return null; // only meaningful for a real decline heading toward zero

  const zeroCrossIndex = -intercept / slope;
  const periodsAway = Math.round(zeroCrossIndex - (values.length - 1));
  if (periodsAway <= 0 || periodsAway > 24) return null; // not a plausible near-term horizon

  const lastLabel = String(sorted[sorted.length - 1][dateCol]);
  const unit = /^\d{4}-\d{1,2}-\d{1,2}$/.test(lastLabel) ? 'days'
    : /^\d{4}-\d{1,2}$/.test(lastLabel) ? 'months'
    : 'periods';

  return {
    column: valueCol.replace(/_/g, ' '),
    periodsAway,
    unit,
    lastValue,
  };
}

/**
 * Flag entities (customers, accounts, stores — any repeated categorical
 * column) that have gone quiet relative to their own historical pace, using
 * only recency math (no ML model) — a classic RFM-style "at risk" signal.
 * Needs a repeated entity-like column and a date column; gracefully returns
 * an empty list on datasets that don't have that shape (e.g. one row per
 * entity, or no dates).
 */
export function recencyRisk(result, maxResults = 5) {
  if (!result?.rows?.length || !result?.columns?.length) return [];
  const { columns, rows } = result;
  const dateCol = detectDateColumn(columns, rows);
  if (!dateCol) return [];

  const numericCols = columns.filter(c => rows.some(r => !Number.isNaN(Number(r[c])) && r[c] !== ''));
  const valueCol = numericCols.find(c => c !== dateCol) || null;

  // Pick the non-numeric, non-date column with the most repeat structure —
  // that's the "entity" (customer/account/store), not a unique row ID.
  const candidateCols = columns.filter(c => c !== dateCol && !numericCols.includes(c));
  let entityCol = null;
  let bestRepeatRatio = 1;
  for (const c of candidateCols) {
    const uniques = new Set(rows.map(r => r[c])).size;
    if (uniques < 2 || uniques === rows.length) continue; // no repeats, not a usable entity axis
    const repeatRatio = rows.length / uniques;
    if (repeatRatio > bestRepeatRatio) {
      bestRepeatRatio = repeatRatio;
      entityCol = c;
    }
  }
  if (!entityCol || bestRepeatRatio < 2) return []; // need real repeat structure to say anything about "recency"

  const parseDate = (v) => {
    const d = new Date(String(v));
    return Number.isNaN(d.getTime()) ? null : d;
  };

  const byEntity = new Map();
  let datasetMaxDate = null;
  for (const r of rows) {
    const d = parseDate(r[dateCol]);
    if (!d) continue;
    if (!datasetMaxDate || d > datasetMaxDate) datasetMaxDate = d;
    const key = String(r[entityCol] ?? '—');
    if (!byEntity.has(key)) byEntity.set(key, { dates: [], total: 0 });
    const entry = byEntity.get(key);
    entry.dates.push(d);
    entry.total += valueCol ? (Number(r[valueCol]) || 0) : 1;
  }
  if (!datasetMaxDate) return [];

  const DAY_MS = 86400000;
  const atRisk = [];
  for (const [label, { dates, total }] of byEntity) {
    if (dates.length < 2) continue; // need at least 2 visits to know a "normal" pace
    dates.sort((a, b) => a - b);
    const gaps = [];
    for (let i = 1; i < dates.length; i++) gaps.push((dates[i] - dates[i - 1]) / DAY_MS);
    const avgGap = gaps.reduce((a, b) => a + b, 0) / gaps.length;
    const lastSeen = dates[dates.length - 1];
    const daysSince = (datasetMaxDate - lastSeen) / DAY_MS;

    // Quiet relative to their OWN normal pace, not an arbitrary global cutoff.
    if (daysSince > Math.max(avgGap * 2, 14)) {
      atRisk.push({ label, daysSince: Math.round(daysSince), avgGap: Math.round(avgGap), total });
    }
  }

  return atRisk.sort((a, b) => b.total - a.total).slice(0, maxResults);
}

/**
 * Build a list of plain-English callouts about the result — period change,
 * outliers, correlation — computed directly from the data (not the LLM),
 * so they're always accurate even on a small local model.
 */
export function buildCallouts(result) {
  if (!result?.rows?.length || !result?.columns?.length) return [];
  const { rows } = result;
  const analysis = analyzeResult(result, '', '');
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
