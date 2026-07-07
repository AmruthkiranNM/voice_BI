/**
 * chartRecommender.js
 * Intelligently recommends the best chart type based on the query result
 * and detected intent/keywords. No backend calls — pure data inspection.
 */

const TIME_PATTERN = /^\d{4}[-/]|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/i;
const DATE_COL_NAMES = /date|month|year|week|quarter|period|time|day/i;

const INTENT_MAP = {
  trend: 'line',
  growth: 'area',
  over_time: 'line',
  time_series: 'line',
  monthly: 'area',
  quarterly: 'area',
  yearly: 'area',
  ranking: 'horizontalBar',
  top: 'horizontalBar',
  bottom: 'horizontalBar',
  distribution: 'donut',
  breakdown: 'donut',
  composition: 'donut',
  share: 'donut',
  proportion: 'donut',
  comparison: 'bar',
  compare: 'bar',
  correlation: 'scatter',
  relationship: 'scatter',
  contribution: 'treemap',
  category: 'treemap',
  funnel: 'funnel',
  conversion: 'funnel',
  scatter: 'scatter',
  bubble: 'bubble',
  heatmap: 'heatmap',
  radar: 'radar',
  waterfall: 'waterfall',
  gauge: 'gauge',
  kpi: 'kpiCard',
  summary: 'kpiCard',
  total: 'kpiCard',
};

const KEYWORD_MAP = {
  trend: 'line',
  over: 'line',
  monthly: 'area',
  yearly: 'area',
  growth: 'area',
  top: 'horizontalBar',
  best: 'horizontalBar',
  worst: 'horizontalBar',
  rank: 'horizontalBar',
  ranked: 'horizontalBar',
  distribution: 'donut',
  breakdown: 'donut',
  share: 'donut',
  portion: 'donut',
  compare: 'bar',
  comparison: 'bar',
  scatter: 'scatter',
  correlation: 'scatter',
  treemap: 'treemap',
  contribution: 'treemap',
  heatmap: 'heatmap',
  funnel: 'funnel',
  waterfall: 'waterfall',
  gauge: 'gauge',
};

function inspectData(result) {
  const { columns = [], rows = [] } = result || {};
  if (!columns.length || !rows.length) return null;

  const numericCols = columns.filter(c =>
    rows.some(r => r[c] != null && r[c] !== '' && !Number.isNaN(Number(r[c]))),
  );
  const labelCols = columns.filter(c => !numericCols.includes(c));
  const labelCol = labelCols[0] || columns[0];

  const labels = rows.map(r => String(r[labelCol] ?? ''));
  const isTimeSeries =
    labels.some(l => TIME_PATTERN.test(l)) ||
    columns.some(c => DATE_COL_NAMES.test(c));

  const rowCount = rows.length;
  const numericCount = numericCols.length;

  return {
    isTimeSeries,
    rowCount,
    numericCount,
    numericCols,
    labelCol,
    isSingleValue: rowCount === 1 && numericCount >= 1,
    isFewRows: rowCount <= 6,
    isManyRows: rowCount > 12,
    hasMultiMetrics: numericCount >= 2,
  };
}

export function recommendChartType(result, intent, query = '') {
  const info = inspectData(result);
  if (!info) return { type: 'bar', confidence: 0, reason: 'No data' };

  const { isTimeSeries, rowCount, numericCount, isSingleValue, isFewRows, isManyRows, hasMultiMetrics } = info;

  if (isSingleValue && numericCount === 1 && rowCount === 1) {
    return { type: 'kpiCard', confidence: 0.99, reason: 'Single KPI value' };
  }

  if (intent) {
    const intentKey = intent.toLowerCase().replace(/\s+/g, '_');
    for (const [k, v] of Object.entries(INTENT_MAP)) {
      if (intentKey.includes(k)) return { type: v, confidence: 0.92, reason: `Intent: ${intent}` };
    }
  }

  if (query) {
    const q = query.toLowerCase();
    for (const [k, v] of Object.entries(KEYWORD_MAP)) {
      if (q.includes(k)) return { type: v, confidence: 0.85, reason: `Keyword: ${k}` };
    }
  }

  if (isTimeSeries) {
    if (hasMultiMetrics) return { type: 'multiLine', confidence: 0.88, reason: 'Time series with multiple metrics' };
    return { type: 'area', confidence: 0.88, reason: 'Time series data detected' };
  }
  if (isFewRows && numericCount === 1) {
    return { type: 'donut', confidence: 0.82, reason: 'Few categories — composition view' };
  }
  if (isManyRows && numericCount === 1) {
    return { type: 'horizontalBar', confidence: 0.82, reason: 'Ranking / many items' };
  }
  if (hasMultiMetrics && rowCount <= 8) {
    return { type: 'groupedBar', confidence: 0.78, reason: 'Multi-metric comparison' };
  }
  if (numericCount >= 2) {
    return { type: 'scatter', confidence: 0.72, reason: 'Two numeric columns — correlation' };
  }

  return { type: 'bar', confidence: 0.6, reason: 'Default bar chart' };
}

/* ═══════════════════════════════════════════════════════════
   DATA-AWARE CHART COMPATIBILITY
   Returns { [chartTypeId]: { enabled, recommended, reason } }
═══════════════════════════════════════════════════════════ */

export function getChartCompatibility(result, intent, query = '') {
  const info = inspectData(result);
  const rec = recommendChartType(result, intent, query);

  const compat = {};
  for (const ct of ALL_CHART_TYPES) {
    compat[ct.id] = { enabled: false, recommended: false, reason: '' };
  }

  if (!info) {
    // No data — disable everything
    for (const id of Object.keys(compat)) {
      compat[id].reason = 'No data available to visualize.';
    }
    return compat;
  }

  const { rowCount, numericCount, isTimeSeries, isFewRows, hasMultiMetrics } = info;
  const hasData = rowCount >= 1 && numericCount >= 1;

  for (const ct of ALL_CHART_TYPES) {
    const id = ct.id;
    if (!hasData) {
      compat[id].reason = 'No numeric data available.';
      continue;
    }

    switch (id) {
      // ── Bar family ──
      case 'bar':
      case 'horizontalBar':
        compat[id].enabled = true;
        compat[id].reason = rowCount > 8
          ? 'Good for ranking many items.'
          : 'Good for comparing categories.';
        break;

      case 'groupedBar':
        if (numericCount >= 2) {
          compat[id].enabled = true;
          compat[id].reason = 'Compares multiple metrics side by side.';
        } else {
          compat[id].reason = 'Requires at least 2 numeric columns.';
        }
        break;

      case 'stackedBar':
        if (numericCount >= 2) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows composition across categories.';
        } else {
          compat[id].reason = 'Requires at least 2 numeric columns.';
        }
        break;

      // ── Line family ──
      case 'line':
        compat[id].enabled = rowCount >= 2;
        compat[id].reason = rowCount >= 2
          ? 'Good for trends and sequences.'
          : 'Requires at least 2 data points.';
        break;

      case 'multiLine':
        if (numericCount >= 2 && rowCount >= 2) {
          compat[id].enabled = true;
          compat[id].reason = 'Compares trends across metrics.';
        } else {
          compat[id].reason = numericCount < 2
            ? 'Requires at least 2 numeric columns.'
            : 'Requires at least 2 data points.';
        }
        break;

      case 'area':
        compat[id].enabled = rowCount >= 2;
        compat[id].reason = rowCount >= 2
          ? 'Shows trends with magnitude.'
          : 'Requires at least 2 data points.';
        break;

      case 'stackedArea':
        if (numericCount >= 2 && rowCount >= 2) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows composition change over time.';
        } else {
          compat[id].reason = numericCount < 2
            ? 'Requires at least 2 numeric columns.'
            : 'Requires at least 2 data points.';
        }
        break;

      case 'cumulative':
        compat[id].enabled = rowCount >= 2;
        compat[id].reason = rowCount >= 2
          ? 'Shows running total over sequence.'
          : 'Requires at least 2 data points.';
        break;

      // ── Part-of-whole ──
      case 'donut':
      case 'pie':
        if (rowCount > 20) {
          compat[id].enabled = true;
          compat[id].reason = 'Too many categories for ideal display. Consider Horizontal Bar or Treemap.';
        } else if (rowCount >= 2) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows proportion of each category.';
        } else {
          compat[id].reason = 'Requires at least 2 categories.';
        }
        break;

      case 'treemap':
        compat[id].enabled = rowCount >= 2;
        compat[id].reason = rowCount >= 2
          ? 'Shows hierarchical composition by area.'
          : 'Requires at least 2 categories.';
        break;

      case 'funnel':
        compat[id].enabled = rowCount >= 2 && rowCount <= 12;
        compat[id].reason = rowCount < 2
          ? 'Requires at least 2 stages.'
          : rowCount > 12
            ? 'Too many items for a funnel. Try Horizontal Bar.'
            : 'Shows stages or sequential filtering.';
        break;

      // ── Advanced ──
      case 'scatter':
        if (numericCount >= 2) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows correlation between two numeric dimensions.';
        } else {
          compat[id].reason = 'Not suitable — requires at least 2 numeric columns.';
        }
        break;

      case 'bubble':
        if (numericCount >= 3) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows three numeric dimensions.';
        } else {
          compat[id].reason = `Not suitable — requires 3 numeric columns, found ${numericCount}.`;
        }
        break;

      case 'radar':
        if (rowCount >= 3 && rowCount <= 12) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows multi-dimensional profile.';
        } else {
          compat[id].reason = rowCount < 3
            ? 'Requires at least 3 categories for radial axes.'
            : 'Too many categories for readable radar. Try Bar.';
        }
        break;

      case 'heatmap':
        if (numericCount >= 2 && rowCount >= 3) {
          compat[id].enabled = true;
          compat[id].reason = 'Matrix view of metric values.';
        } else {
          compat[id].reason = numericCount < 2
            ? 'Requires at least 2 numeric columns.'
            : 'Requires at least 3 rows.';
        }
        break;

      case 'waterfall':
        compat[id].enabled = rowCount >= 2;
        compat[id].reason = rowCount >= 2
          ? 'Shows incremental positive/negative changes.'
          : 'Requires at least 2 data points.';
        break;

      case 'gauge':
        if (rowCount === 1 && numericCount >= 1) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows single value on a gauge.';
        } else {
          compat[id].reason = rowCount !== 1
            ? 'Gauge requires exactly 1 row of data.'
            : 'Requires at least 1 numeric column.';
        }
        break;

      case 'kpiCard':
        if (rowCount <= 3 && numericCount >= 1) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows key metrics as cards.';
        } else {
          compat[id].reason = 'Best for 1–3 rows of aggregated metrics.';
        }
        break;

      default:
        compat[id].enabled = true;
        compat[id].reason = '';
    }
  }

  // Mark the recommended type
  if (rec.type && compat[rec.type]) {
    compat[rec.type].recommended = true;
  }

  return compat;
}

/* ═══════════════════════════════════════════════════════════
   Suggest alternatives when a chart type is unsupported
═══════════════════════════════════════════════════════════ */
export function suggestAlternatives(result, intent, query = '') {
  const compat = getChartCompatibility(result, intent, query);
  const rec = recommendChartType(result, intent, query);

  const alternatives = ALL_CHART_TYPES
    .filter(ct => compat[ct.id]?.enabled && ct.id !== 'kpiCard')
    .slice(0, 4)
    .map(ct => ct.label);

  return {
    recommended: rec.type,
    recommendedLabel: ALL_CHART_TYPES.find(t => t.id === rec.type)?.label || rec.type,
    alternatives,
  };
}


export const CHART_TYPE_GROUPS = [
  {
    label: 'Bar',
    types: [
      { id: 'bar', label: 'Vertical Bar' },
      { id: 'horizontalBar', label: 'Horizontal Bar' },
      { id: 'groupedBar', label: 'Grouped Bar' },
      { id: 'stackedBar', label: 'Stacked Bar' },
    ],
  },
  {
    label: 'Line / Area',
    types: [
      { id: 'line', label: 'Line' },
      { id: 'multiLine', label: 'Multi-Line' },
      { id: 'area', label: 'Area' },
      { id: 'stackedArea', label: 'Stacked Area' },
      { id: 'cumulative', label: 'Cumulative' },
    ],
  },
  {
    label: 'Part of Whole',
    types: [
      { id: 'donut', label: 'Donut' },
      { id: 'pie', label: 'Pie' },
      { id: 'treemap', label: 'Treemap' },
      { id: 'funnel', label: 'Funnel' },
    ],
  },
  {
    label: 'Advanced',
    types: [
      { id: 'scatter', label: 'Scatter' },
      { id: 'bubble', label: 'Bubble' },
      { id: 'radar', label: 'Radar' },
      { id: 'heatmap', label: 'Heatmap' },
      { id: 'waterfall', label: 'Waterfall' },
      { id: 'gauge', label: 'Gauge' },
    ],
  },
];

export const ALL_CHART_TYPES = CHART_TYPE_GROUPS.flatMap(g => g.types);
