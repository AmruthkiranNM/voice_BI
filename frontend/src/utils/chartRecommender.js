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
