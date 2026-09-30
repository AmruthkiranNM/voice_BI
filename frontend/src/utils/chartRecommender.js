/**
 * chartRecommender.js
 * Intelligently recommends the best chart type based on the query result
 * and detected intent/keywords/semantic specification.
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
  monthly: 'line',
  yearly: 'line',
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
  percentage: 'donut',
  percent: 'donut',
  compare: 'bar',
  comparison: 'bar',
  scatter: 'scatter',
  correlation: 'scatter',
  relationship: 'scatter',
  treemap: 'treemap',
  contribution: 'treemap',
  split: 'stackedBar',
  cumulative: 'cumulative',
  heatmap: 'heatmap',
  funnel: 'funnel',
  waterfall: 'waterfall',
  gauge: 'gauge',
};

export function inspectData(result) {
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

export function recommendChartType(result, intent, query = '', spec = null) {
  const info = inspectData(result);
  if (!info) return { type: 'bar', confidence: 0, reason: 'No data' };

  const { isTimeSeries, rowCount, numericCount, isSingleValue, isFewRows, hasMultiMetrics } = info;
  const q = query.toLowerCase();

  // 1. Single Value
  if (isSingleValue && numericCount === 1 && rowCount === 1) {
    return { type: 'kpiCard', confidence: 0.99, reason: 'Single KPI value' };
  }

  // 2. Hierarchical (Two categorical dimensions)
  if (spec && spec.isHierarchical) {
    if (q.includes('composition') || q.includes('split') || q.includes('breakdown')) {
      return { type: 'stackedBar', confidence: 0.9, reason: 'Hierarchical composition requested' };
    }
    if (q.includes('share') || q.includes('contribution') || q.includes('percentage')) {
      return { type: 'treemap', confidence: 0.9, reason: 'Hierarchical part-to-whole requested' };
    }
    if (q.includes('rank') || q.includes('top') || q.includes('best')) {
      return { type: 'horizontalBar', confidence: 0.9, reason: 'Hierarchical ranking' };
    }
    // Default hierarchical fallback
    return { type: 'stackedBar', confidence: 0.7, reason: 'Default hierarchical comparison' };
  }

  // 3. Time Series
  if (isTimeSeries) {
    if (q.includes('cumulative')) {
      return { type: 'cumulative', confidence: 0.9, reason: 'Cumulative time series requested' };
    }
    if (hasMultiMetrics || (spec && spec.secondaryDimension)) {
      if (q.includes('composition') || q.includes('share') || q.includes('split')) {
         return { type: 'stackedArea', confidence: 0.9, reason: 'Time series composition' };
      }
      return { type: 'multiLine', confidence: 0.88, reason: 'Time series with multiple metrics/groups' };
    }
    return { type: 'line', confidence: 0.88, reason: 'Standard time series' };
  }

  // 4. Part-to-whole (Pie/Donut)
  if (numericCount === 1 && isFewRows && (q.includes('share') || q.includes('portion') || q.includes('distribution') || q.includes('percent'))) {
    return { type: 'donut', confidence: 0.9, reason: 'Part-to-whole on few categories' };
  }

  // 5. Ranking
  if (numericCount === 1 && (q.includes('top') || q.includes('rank') || q.includes('best') || rowCount > 8)) {
    return { type: 'horizontalBar', confidence: 0.85, reason: 'Ranking or many items' };
  }

  // 6. Relationship (Scatter)
  if (numericCount >= 2 && (q.includes('vs') || q.includes('correlation') || q.includes('relationship') || q.includes('compare'))) {
    return { type: 'scatter', confidence: 0.85, reason: 'Comparing multiple metrics' };
  }

  // 7. Multi-metric comparison (Grouped bar)
  if (numericCount >= 2 && rowCount <= 8) {
    return { type: 'groupedBar', confidence: 0.8, reason: 'Multi-metric categorical comparison' };
  }

  // 8. Intent/Keyword fallback
  if (intent) {
    const intentKey = intent.toLowerCase().replace(/\s+/g, '_');
    for (const [k, v] of Object.entries(INTENT_MAP)) {
      if (intentKey.includes(k)) return { type: v, confidence: 0.7, reason: `Intent matches ${k}` };
    }
  }

  for (const [k, v] of Object.entries(KEYWORD_MAP)) {
    if (q.includes(k)) return { type: v, confidence: 0.6, reason: `Keyword matches ${k}` };
  }

  return { type: 'bar', confidence: 0.5, reason: 'Default categorical comparison' };
}

/* ═══════════════════════════════════════════════════════════
   DATA-AWARE CHART COMPATIBILITY
   Returns { [chartTypeId]: { enabled, recommended, reason } }
═══════════════════════════════════════════════════════════ */
export function getChartCompatibility(result, intent, query = '', spec = null) {
  const info = inspectData(result);
  const rec = recommendChartType(result, intent, query, spec);

  const compat = {};
  for (const ct of ALL_CHART_TYPES) {
    compat[ct.id] = { enabled: false, recommended: false, reason: '' };
  }

  if (!info) {
    for (const id of Object.keys(compat)) {
      compat[id].reason = 'No data available to visualize.';
    }
    return compat;
  }

  const { rowCount, numericCount, isTimeSeries, isFewRows, hasMultiMetrics } = info;
  const hasData = rowCount >= 1 && numericCount >= 1;
  const isHierarchical = spec?.isHierarchical;

  for (const ct of ALL_CHART_TYPES) {
    const id = ct.id;
    if (!hasData) {
      compat[id].reason = 'No numeric data available.';
      continue;
    }

    switch (id) {
      // ── Bar family ──
      case 'bar':
        if (isTimeSeries) {
           compat[id].reason = 'Line/Area is better for time series.';
        } else if (isHierarchical) {
           compat[id].reason = 'Use Stacked Bar or Treemap for hierarchical data.';
        } else {
           compat[id].enabled = true;
           compat[id].reason = 'Good for categorical comparison.';
        }
        break;

      case 'horizontalBar':
        if (isTimeSeries) {
           compat[id].reason = 'Horizontal bar is poor for time series.';
        } else {
           compat[id].enabled = true;
           compat[id].reason = 'Good for ranking items.';
        }
        break;

      case 'groupedBar':
        if (numericCount >= 2 || (isHierarchical && !isTimeSeries)) {
          compat[id].enabled = true;
          compat[id].reason = 'Compares metrics/groups side by side.';
        } else {
          compat[id].reason = 'Requires at least 2 numeric columns or hierarchical groups.';
        }
        break;

      case 'stackedBar':
        if (numericCount >= 2 || (isHierarchical && !isTimeSeries)) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows composition across categories.';
        } else {
          compat[id].reason = 'Requires multiple metrics or hierarchical groups.';
        }
        break;

      // ── Line family ──
      case 'line':
        if (isTimeSeries) {
           compat[id].enabled = rowCount >= 2;
           compat[id].reason = rowCount >= 2 ? 'Good for time trends.' : 'Requires 2+ points.';
        } else {
           compat[id].reason = 'Not recommended for unordered categories.';
        }
        break;

      case 'multiLine':
        if (isTimeSeries && (numericCount >= 2 || isHierarchical || spec?.secondaryDimension)) {
          compat[id].enabled = true;
          compat[id].reason = 'Compares trends across metrics or groups.';
        } else {
          compat[id].reason = 'Requires time series with multiple metrics or groups.';
        }
        break;

      case 'area':
        if (isTimeSeries) {
           compat[id].enabled = rowCount >= 2;
           compat[id].reason = rowCount >= 2 ? 'Shows trends with magnitude.' : 'Requires 2+ points.';
        } else {
           compat[id].reason = 'Not recommended for unordered categories.';
        }
        break;

      case 'stackedArea':
        if (isTimeSeries && (numericCount >= 2 || isHierarchical || spec?.secondaryDimension)) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows composition change over time.';
        } else {
          compat[id].reason = 'Requires time series with multiple metrics or groups.';
        }
        break;

      case 'cumulative':
        if (isTimeSeries) {
           compat[id].enabled = rowCount >= 2;
           compat[id].reason = rowCount >= 2 ? 'Shows running total over time.' : 'Requires 2+ points.';
        } else {
           compat[id].reason = 'Requires time-ordered data.';
        }
        break;

      // ── Part-of-whole ──
      case 'donut':
      case 'pie':
        if (isHierarchical) {
           compat[id].reason = 'Use Treemap for hierarchical part-to-whole.';
        } else if (isTimeSeries) {
           compat[id].reason = 'Use Line/Area for time series.';
        } else if (rowCount > 10) {
           compat[id].reason = 'Too many categories. Use Bar or Treemap.';
        } else if (rowCount >= 2 && numericCount === 1) {
           compat[id].enabled = true;
           compat[id].reason = 'Shows proportion of each category.';
        } else {
           compat[id].reason = 'Requires 2-10 categories and exactly 1 metric.';
        }
        break;

      case 'treemap':
        if (isHierarchical || (rowCount >= 2 && numericCount === 1 && !isTimeSeries)) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows hierarchical composition by area.';
        } else {
          compat[id].reason = 'Requires hierarchical or categorical data.';
        }
        break;

      case 'funnel':
        if (!isTimeSeries && !isHierarchical && rowCount >= 2 && rowCount <= 12) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows sequential filtering.';
        } else {
          compat[id].reason = 'Requires 2-12 categorical stages.';
        }
        break;

      // ── Advanced ──
      case 'scatter':
        if (numericCount >= 2 && !isTimeSeries) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows correlation between two numeric dimensions.';
        } else {
          compat[id].reason = 'Requires at least 2 numeric columns, not optimal for time series.';
        }
        break;

      case 'bubble':
        if (numericCount >= 3) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows three numeric dimensions.';
        } else {
          compat[id].reason = `Requires 3 numeric columns, found ${numericCount}.`;
        }
        break;

      case 'radar':
        if (!isTimeSeries && !isHierarchical && rowCount >= 3 && rowCount <= 12) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows multi-dimensional profile.';
        } else {
          compat[id].reason = 'Requires 3-12 categories.';
        }
        break;

      case 'heatmap':
        if (numericCount >= 2 && rowCount >= 3) {
          compat[id].enabled = true;
          compat[id].reason = 'Matrix view of metric values.';
        } else {
          compat[id].reason = 'Requires at least 2 numeric columns and 3 rows.';
        }
        break;

      case 'waterfall':
        if (isTimeSeries) {
          compat[id].enabled = rowCount >= 2;
          compat[id].reason = 'Shows incremental positive/negative changes.';
        } else {
          compat[id].reason = 'Requires ordered sequential data.';
        }
        break;

      case 'gauge':
        if (rowCount === 1 && numericCount >= 1) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows single value on a gauge.';
        } else {
          compat[id].reason = 'Gauge requires exactly 1 row of data.';
        }
        break;

      case 'kpiCard':
        if (rowCount <= 3 && numericCount >= 1) {
          compat[id].enabled = true;
          compat[id].reason = 'Shows key metrics as cards.';
        } else {
          compat[id].reason = 'Best for 1-3 rows of aggregated metrics.';
        }
        break;

      default:
        compat[id].enabled = true;
        compat[id].reason = '';
    }
  }

  if (rec.type && compat[rec.type]) {
    compat[rec.type].recommended = true;
  }

  return compat;
}

export function suggestAlternatives(result, intent, query = '', spec = null) {
  const compat = getChartCompatibility(result, intent, query, spec);
  const rec = recommendChartType(result, intent, query, spec);

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
