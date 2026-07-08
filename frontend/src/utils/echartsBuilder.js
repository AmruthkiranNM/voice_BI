/**
 * echartsBuilder.js
 * Builds complete ECharts `option` objects for all supported chart types.
 * Receives pre-prepared labels/datasets and returns ready-to-render configs.
 */

import { BI_COLORS, getPalette, getColor, hexToRgba, ECHARTS_TOOLTIP_STYLE, ECHARTS_AXIS_STYLE, ECHARTS_LEGEND_STYLE } from './biPalette';

/* ═══════════════════════════════════════════════════════════
   FORMATTERS
═══════════════════════════════════════════════════════════ */
const fmt = (v) => {
  if (v == null || Number.isNaN(v)) return '—';
  const n = Number(v);
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  if (!Number.isInteger(n)) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return n.toLocaleString();
};

const fmtFull = (v) => {
  if (v == null || Number.isNaN(v)) return '—';
  const n = Number(v);
  if (!Number.isInteger(n)) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return n.toLocaleString();
};

/** Detect if column name suggests currency */
const isCurrencyCol = (name) => /revenue|sales|profit|amount|price|cost|income|earning|spend|fee|salary|wage|budget/i.test(name);
/** Detect if column name suggests percentage */
const isPercentCol = (name) => /rate|percent|pct|ratio|margin|share|proportion/i.test(name);

const fmtValue = (v, colName) => {
  if (v == null || Number.isNaN(v)) return '—';
  const n = Number(v);
  if (isPercentCol(colName || '')) return `${n.toFixed(1)}%`;
  if (isCurrencyCol(colName || '')) return `$${fmt(n)}`;
  return fmt(n);
};

const fmtValueFull = (v, colName) => {
  if (v == null || Number.isNaN(v)) return '—';
  const n = Number(v);
  if (isPercentCol(colName || '')) return `${n.toFixed(2)}%`;
  if (isCurrencyCol(colName || '')) return `$${fmtFull(n)}`;
  return fmtFull(n);
};

/* ═══════════════════════════════════════════════════════════
   TOOLTIPS
═══════════════════════════════════════════════════════════ */
const richTooltip = (labels, datasets) => ({
  trigger: 'axis',
  ...ECHARTS_TOOLTIP_STYLE,
  formatter: (params) => {
    if (!params?.length) return '';
    const name = params[0].name;
    const total = params.reduce((s, p) => s + (Number(p.value) || 0), 0);
    const rows = params.map(p => {
      const val = Number(p.value) || 0;
      const ds = datasets.find(d => d.label === p.seriesName);
      const colName = ds?.originalColumn || '';
      const allVals = (ds?.data || []).map(Number).filter(x => !Number.isNaN(x));
      const avg = allVals.length ? allVals.reduce((a, b) => a + b, 0) / allVals.length : 0;
      const diff = avg ? ((val - avg) / Math.abs(avg)) * 100 : 0;
      const pct = total ? ((val / total) * 100).toFixed(1) : null;
      return `
        <div style="display:flex;align-items:center;gap:8px;margin:3px 0;">
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};"></span>
          <span style="color:#9ca3af;font-size:11px;">${p.seriesName}</span>
          <span style="margin-left:auto;font-weight:600;color:#f2f2ee;">${fmtValueFull(val, colName)}</span>
          ${pct != null ? `<span style="color:#6b7280;font-size:10px;">${pct}%</span>` : ''}
          <span style="color:${diff >= 0 ? '#3b82f6' : '#f87171'};font-size:10px;">${diff >= 0 ? '▲' : '▼'} ${Math.abs(diff).toFixed(1)}% avg</span>
        </div>`;
    }).join('');
    return `<div style="min-width:220px;"><div style="font-size:12px;font-weight:600;color:#f2f2ee;margin-bottom:6px;padding-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.08);">${name}</div>${rows}</div>`;
  },
});

const itemTooltip = (datasets) => ({
  trigger: 'item',
  ...ECHARTS_TOOLTIP_STYLE,
  formatter: (p) => {
    const ds = datasets[0];
    const colName = ds?.originalColumn || '';
    const allVals = (ds?.data || []).map(Number).filter(x => !Number.isNaN(x));
    const total = allVals.reduce((a, b) => a + b, 0);
    const val = Number(p.value) || 0;
    const pct = total ? ((val / total) * 100).toFixed(1) : null;
    const sortedVals = [...allVals].sort((a, b) => b - a);
    const rank = sortedVals.indexOf(val) + 1;
    return `<div style="min-width:200px;">
      <div style="font-weight:600;color:#f2f2ee;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.08);">${p.name}</div>
      <div style="display:flex;justify-content:space-between;gap:12px;margin:3px 0;"><span style="color:#9ca3af;">Value</span><span style="font-weight:600;color:#f2f2ee;">${fmtValueFull(val, colName)}</span></div>
      ${pct != null ? `<div style="display:flex;justify-content:space-between;gap:12px;margin:3px 0;"><span style="color:#9ca3af;">Share</span><span style="color:#3b82f6;">${pct}%</span></div>` : ''}
      ${rank ? `<div style="display:flex;justify-content:space-between;gap:12px;margin:3px 0;"><span style="color:#9ca3af;">Rank</span><span style="color:#60a5fa;">#${rank} of ${allVals.length}</span></div>` : ''}
    </div>`;
  },
});

/* ═══════════════════════════════════════════════════════════
   HELPERS
═══════════════════════════════════════════════════════════ */
const baseGrid = (bottom = 60) => ({ left: 16, right: 16, top: 56, bottom, containLabel: true });

function xAxis(labels, opts = {}) {
  return { type: 'category', data: labels, ...ECHARTS_AXIS_STYLE, axisLabel: { ...ECHARTS_AXIS_STYLE.axisLabel, rotate: labels.length > 8 ? 35 : 0, ...opts.axisLabel } };
}
function yAxis(opts = {}) {
  return { type: 'value', ...ECHARTS_AXIS_STYLE, axisLabel: { ...ECHARTS_AXIS_STYLE.axisLabel, formatter: v => fmt(v) }, ...opts };
}

function chartTitle(text, subtext = '') {
  return {
    text,
    subtext,
    left: 12,
    top: 8,
    textStyle: { color: '#f2f2ee', fontSize: 13, fontWeight: 600, fontFamily: 'Inter, system-ui, sans-serif' },
    subtextStyle: { color: '#6b7280', fontSize: 11, fontFamily: 'Inter, system-ui, sans-serif' },
  };
}

const dataZoom = [
  { type: 'inside', xAxisIndex: 0, zoomOnMouseWheel: true },
  { type: 'slider', height: 20, bottom: 4, fillerColor: 'rgba(59,130,246,0.08)', borderColor: 'rgba(255,255,255,0.08)', handleStyle: { color: '#3b82f6' }, textStyle: { color: '#6b7280' } },
];

const animationConfig = { animation: true, animationDuration: 600, animationEasing: 'cubicOut', animationDurationUpdate: 400, animationEasingUpdate: 'cubicInOut' };

/** Group small pie/donut slices into "Others" */
function groupSmallSlices(pieData, maxSlices = 8) {
  if (pieData.length <= maxSlices) return pieData;
  const sorted = [...pieData].sort((a, b) => b.value - a.value);
  const top = sorted.slice(0, maxSlices - 1);
  const rest = sorted.slice(maxSlices - 1);
  const othersValue = rest.reduce((s, d) => s + d.value, 0);
  top.push({ name: `Others (${rest.length} items)`, value: othersValue });
  return top;
}

/** Compute cumulative sum */
function cumulativeData(data) {
  let running = 0;
  return data.map(v => { running += (Number(v) || 0); return running; });
}

/* ═══════════════════════════════════════════════════════════
   MAIN BUILDER
═══════════════════════════════════════════════════════════ */
export function buildEChartsOption(type, labels, datasets, extra = {}) {
  const colors = getPalette(Math.max(datasets.length, labels.length));
  const showLegend = datasets.length > 1;
  const labelColName = extra.labelCol || 'Category';
  const primaryMetric = datasets[0]?.label || 'Value';

  const legend = { ...ECHARTS_LEGEND_STYLE, data: datasets.map(d => d.label), top: 8, type: 'scroll' };
  const toolbox = {
    right: 8, top: 4,
    feature: {
      saveAsImage: { title: 'Save PNG', icon: 'path://M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z', name: 'chart' },
      dataZoom: { title: { zoom: 'Zoom', back: 'Reset' } },
      restore: { title: 'Reset' },
    },
    iconStyle: { color: '#6b7280', borderColor: 'transparent' },
    emphasis: { iconStyle: { color: '#3b82f6' } },
  };

  switch (type) {

    case 'bar':
      return {
        color: colors,
        title: chartTitle('Vertical Bar', `${primaryMetric} by ${labelColName}`),
        tooltip: richTooltip(labels, datasets), legend: showLegend ? legend : { show: false },
        toolbox, grid: baseGrid(labels.length > 8 ? 80 : 60),
        xAxis: { ...xAxis(labels), name: labelColName, nameLocation: 'middle', nameGap: labels.length > 8 ? 55 : 35, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        yAxis: { ...yAxis(), name: primaryMetric, nameLocation: 'middle', nameGap: 50, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        dataZoom: labels.length > 10 ? dataZoom : [],
        series: datasets.map((ds, i) => ({
          name: ds.label, type: 'bar', data: ds.data, barMaxWidth: 48,
          itemStyle: { color: colors[i], borderRadius: [4, 4, 0, 0] },
          emphasis: { itemStyle: { color: getColor(i, 1), shadowBlur: 10, shadowColor: hexToRgba(colors[i], 0.4) } },
          label: { show: extra.showLabels, position: 'top', color: '#9ca3af', fontSize: 10, formatter: p => fmt(p.value) },
        })),
        ...animationConfig,
      };

    case 'horizontalBar':
      return {
        color: colors,
        title: chartTitle('Horizontal Bar', `${primaryMetric} by ${labelColName}`),
        tooltip: richTooltip(labels, datasets), legend: showLegend ? legend : { show: false },
        toolbox, grid: { left: 16, right: 16, top: 56, bottom: 16, containLabel: true },
        xAxis: { type: 'value', ...ECHARTS_AXIS_STYLE, axisLabel: { ...ECHARTS_AXIS_STYLE.axisLabel, formatter: v => fmt(v) }, name: primaryMetric, nameLocation: 'middle', nameGap: 30, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        yAxis: { type: 'category', data: [...labels].reverse(), ...ECHARTS_AXIS_STYLE, axisLabel: { ...ECHARTS_AXIS_STYLE.axisLabel, width: 120, overflow: 'truncate' }, name: labelColName, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        dataZoom: labels.length > 10 ? [{ type: 'inside', yAxisIndex: 0 }, { type: 'slider', yAxisIndex: 0, width: 16, right: 0, fillerColor: 'rgba(59,130,246,0.08)', borderColor: 'rgba(255,255,255,0.08)' }] : [],
        series: datasets.map((ds, i) => ({
          name: ds.label, type: 'bar', data: [...ds.data].reverse(), barMaxWidth: 32,
          itemStyle: { color: colors[i], borderRadius: [0, 4, 4, 0] },
          emphasis: { itemStyle: { shadowBlur: 8, shadowColor: hexToRgba(colors[i], 0.4) } },
          label: { show: extra.showLabels || labels.length <= 15, position: 'right', color: '#9ca3af', fontSize: 10, formatter: p => fmt(p.value) },
        })),
        ...animationConfig,
      };

    case 'groupedBar':
      return {
        color: colors,
        title: chartTitle('Grouped Bar', `Comparing metrics by ${labelColName}`),
        tooltip: richTooltip(labels, datasets), legend,
        toolbox, grid: baseGrid(labels.length > 8 ? 80 : 60),
        xAxis: { ...xAxis(labels), name: labelColName, nameLocation: 'middle', nameGap: labels.length > 8 ? 55 : 35, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        yAxis: yAxis(),
        dataZoom: labels.length > 10 ? dataZoom : [],
        series: datasets.map((ds, i) => ({
          name: ds.label, type: 'bar', data: ds.data, barMaxWidth: 32,
          itemStyle: { color: colors[i], borderRadius: [4, 4, 0, 0] },
          emphasis: { itemStyle: { shadowBlur: 8, shadowColor: hexToRgba(colors[i], 0.4) } },
        })),
        ...animationConfig,
      };

    case 'stackedBar':
      return {
        color: colors,
        title: chartTitle('Stacked Bar', `Composition of metrics by ${labelColName}`),
        tooltip: { ...richTooltip(labels, datasets), trigger: 'axis', axisPointer: { type: 'shadow' } },
        legend, toolbox, grid: baseGrid(labels.length > 8 ? 80 : 60),
        xAxis: { ...xAxis(labels), name: labelColName, nameLocation: 'middle', nameGap: labels.length > 8 ? 55 : 35, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        yAxis: yAxis(),
        series: datasets.map((ds, i) => ({
          name: ds.label, type: 'bar', stack: 'total', data: ds.data,
          itemStyle: { color: colors[i] },
          emphasis: { focus: 'series' },
          label: { show: false },
        })),
        ...animationConfig,
      };

    case 'line':
    case 'multiLine':
      return {
        color: colors,
        title: chartTitle(type === 'multiLine' ? 'Multi-Line Comparison' : 'Line Chart', `${primaryMetric} across ${labelColName}`),
        tooltip: richTooltip(labels, datasets), legend: showLegend ? legend : { show: false },
        toolbox, grid: baseGrid(labels.length > 8 ? 80 : 60),
        xAxis: { ...xAxis(labels), name: labelColName, nameLocation: 'middle', nameGap: labels.length > 8 ? 55 : 35, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        yAxis: { ...yAxis(), name: primaryMetric, nameLocation: 'middle', nameGap: 50, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        dataZoom: labels.length > 10 ? dataZoom : [],
        series: datasets.map((ds, i) => ({
          name: ds.label, type: 'line', data: ds.data, smooth: 0.4,
          symbol: 'circle', symbolSize: 5,
          lineStyle: { width: 2.5, color: colors[i] },
          itemStyle: { color: colors[i], borderWidth: 2, borderColor: '#09090b' },
          emphasis: { scale: true, focus: 'series' },
          label: { show: extra.showLabels, position: 'top', color: '#9ca3af', fontSize: 9, formatter: p => fmt(p.value) },
        })),
        ...animationConfig,
      };

    case 'area':
    case 'stackedArea':
      return {
        color: colors,
        title: chartTitle(type === 'stackedArea' ? 'Stacked Area' : 'Area Chart', `${primaryMetric} trend across ${labelColName}`),
        tooltip: richTooltip(labels, datasets), legend: showLegend ? legend : { show: false },
        toolbox, grid: baseGrid(labels.length > 8 ? 80 : 60),
        xAxis: { ...xAxis(labels), name: labelColName, nameLocation: 'middle', nameGap: labels.length > 8 ? 55 : 35, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        yAxis: { ...yAxis(), name: primaryMetric, nameLocation: 'middle', nameGap: 50, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        dataZoom: labels.length > 10 ? dataZoom : [],
        series: datasets.map((ds, i) => ({
          name: ds.label, type: 'line', data: ds.data, smooth: 0.4,
          stack: type === 'stackedArea' ? 'total' : undefined,
          areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: hexToRgba(colors[i], 0.35) }, { offset: 1, color: hexToRgba(colors[i], 0.02) }] } },
          lineStyle: { width: 2.5, color: colors[i] },
          symbol: 'circle', symbolSize: 4,
          itemStyle: { color: colors[i] },
          emphasis: { focus: 'series' },
        })),
        ...animationConfig,
      };

    case 'cumulative': {
      const cumDatasets = datasets.map(ds => ({
        ...ds,
        data: cumulativeData(ds.data),
      }));
      return {
        color: colors,
        title: chartTitle('Cumulative Total', `Running total of ${primaryMetric} across ${labelColName}`),
        tooltip: {
          trigger: 'axis',
          ...ECHARTS_TOOLTIP_STYLE,
          formatter: (params) => {
            if (!params?.length) return '';
            const name = params[0].name;
            const rows = params.map(p => {
              const val = Number(p.value) || 0;
              return `<div style="display:flex;align-items:center;gap:8px;margin:3px 0;">
                <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};"></span>
                <span style="color:#9ca3af;font-size:11px;">${p.seriesName} (cumulative)</span>
                <span style="margin-left:auto;font-weight:600;color:#f2f2ee;">${fmtFull(val)}</span>
              </div>`;
            }).join('');
            return `<div style="min-width:220px;"><div style="font-size:12px;font-weight:600;color:#f2f2ee;margin-bottom:6px;padding-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.08);">${name}</div>${rows}</div>`;
          },
        },
        legend: showLegend ? legend : { show: false },
        toolbox, grid: baseGrid(labels.length > 8 ? 80 : 60),
        xAxis: { ...xAxis(labels), name: labelColName, nameLocation: 'middle', nameGap: labels.length > 8 ? 55 : 35, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        yAxis: { ...yAxis(), name: `${primaryMetric} (Cumulative)`, nameLocation: 'middle', nameGap: 60, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        dataZoom: labels.length > 10 ? dataZoom : [],
        series: cumDatasets.map((ds, i) => ({
          name: ds.label, type: 'line', data: ds.data, smooth: 0.3,
          symbol: 'circle', symbolSize: 5,
          lineStyle: { width: 2.5, color: colors[i] },
          areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: hexToRgba(colors[i], 0.25) }, { offset: 1, color: hexToRgba(colors[i], 0.02) }] } },
          itemStyle: { color: colors[i], borderWidth: 2, borderColor: '#09090b' },
          emphasis: { scale: true, focus: 'series' },
          label: { show: extra.showLabels, position: 'top', color: '#9ca3af', fontSize: 9, formatter: p => fmt(p.value) },
        })),
        ...animationConfig,
      };
    }

    case 'donut':
    case 'pie': {
      const rawPieData = labels.map((l, i) => ({ name: l, value: Math.abs(datasets[0]?.data[i] ?? 0) }));
      const pieData = groupSmallSlices(rawPieData, 10);
      const pieTotal = pieData.reduce((s, d) => s + d.value, 0);
      const isDonut = type === 'donut';

      return {
        color: colors,
        title: chartTitle(isDonut ? 'Donut Chart' : 'Pie Chart', `${primaryMetric} distribution`),
        tooltip: itemTooltip(datasets),
        legend: {
          ...ECHARTS_LEGEND_STYLE,
          orient: 'vertical',
          right: 16,
          top: 56,
          bottom: 20,
          data: pieData.map(d => d.name),
          type: 'scroll',
          pageButtonPosition: 'end',
          selectedMode: true,
        },
        toolbox,
        // Center text for donut
        ...(isDonut ? {
          graphic: [{
            type: 'group',
            left: 'center',
            top: 'middle',
            children: [
              {
                type: 'text',
                style: {
                  text: fmt(pieTotal),
                  fill: '#f2f2ee',
                  fontSize: 22,
                  fontWeight: 700,
                  fontFamily: 'JetBrains Mono, monospace',
                  textAlign: 'center',
                },
                left: 'center',
                top: -12,
              },
              {
                type: 'text',
                style: {
                  text: 'Total',
                  fill: '#6b7280',
                  fontSize: 11,
                  fontFamily: 'Inter, system-ui, sans-serif',
                  textAlign: 'center',
                },
                left: 'center',
                top: 14,
              },
            ],
          }],
        } : {}),
        series: [{
          name: datasets[0]?.label || 'Value', type: 'pie',
          radius: isDonut ? ['42%', '70%'] : '70%',
          center: ['42%', '54%'],
          data: pieData,
          label: {
            show: true,
            formatter: p => p.percent > 4 ? `${p.name}\n${p.percent.toFixed(1)}%` : '',
            color: '#9ca3af',
            fontSize: 10,
            lineHeight: 14,
          },
          labelLine: { length: 12, length2: 8, lineStyle: { color: 'rgba(255,255,255,0.15)' } },
          emphasis: {
            scale: true,
            scaleSize: 8,
            focus: 'self',
            blurScope: 'coordinateSystem',
            itemStyle: { shadowBlur: 20, shadowColor: 'rgba(59,130,246,0.4)' },
          },
          itemStyle: { borderColor: '#09090b', borderWidth: 2, borderRadius: 4 },
          animationType: 'scale',
          animationEasing: 'elasticOut',
        }],
        ...animationConfig,
      };
    }

    case 'treemap': {
      const tmData = labels.slice(0, 30).map((l, i) => ({ name: l, value: Math.abs(datasets[0]?.data[i] ?? 0) }))
        .sort((a, b) => b.value - a.value);
      return {
        color: colors,
        title: chartTitle('Treemap', `${primaryMetric} by ${labelColName} — sized by value`),
        tooltip: { ...ECHARTS_TOOLTIP_STYLE, trigger: 'item', formatter: p => `<b>${p.name}</b><br/>${fmtValueFull(p.value, datasets[0]?.originalColumn)}` },
        toolbox,
        series: [{
          name: datasets[0]?.label || 'Value', type: 'treemap', data: tmData,
          top: 48,
          roam: false, nodeClick: 'zoomToNode',
          label: { show: true, formatter: p => `${p.name}\n${fmt(p.value)}`, color: '#09090b', fontWeight: 600, fontSize: 11 },
          itemStyle: { borderColor: '#09090b', borderWidth: 2, gapWidth: 3 },
          emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(59,130,246,0.4)' } },
          breadcrumb: { show: true, bottom: 4, height: 20, itemStyle: { color: '#1f2937', textStyle: { color: '#9ca3af' } } },
          levels: [{ color: colors, colorMappingBy: 'index' }],
        }],
        ...animationConfig,
      };
    }

    case 'scatter': {
      const scData = (datasets[0]?.data || []).map((v, i) => [v, datasets[1]?.data[i] ?? 0]);
      const xLabel = datasets[0]?.label || 'X';
      const yLabel = datasets[1]?.label || 'Y';
      return {
        color: colors,
        title: chartTitle('Scatter Plot', `${xLabel} vs ${yLabel}`),
        tooltip: {
          ...ECHARTS_TOOLTIP_STYLE, trigger: 'item',
          formatter: p => `<b>${labels[p.dataIndex] ?? p.dataIndex}</b><br/>${xLabel}: ${fmtFull(p.value[0])}<br/>${yLabel}: ${fmtFull(p.value[1])}`,
        },
        legend: { show: false }, toolbox,
        grid: { left: 60, right: 30, top: 56, bottom: 60, containLabel: true },
        xAxis: { type: 'value', name: xLabel, ...ECHARTS_AXIS_STYLE, axisLabel: { ...ECHARTS_AXIS_STYLE.axisLabel, formatter: v => fmt(v) }, nameLocation: 'middle', nameGap: 35, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        yAxis: { type: 'value', name: yLabel, ...ECHARTS_AXIS_STYLE, axisLabel: { ...ECHARTS_AXIS_STYLE.axisLabel, formatter: v => fmt(v) }, nameLocation: 'middle', nameGap: 50, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        series: [{ type: 'scatter', data: scData, symbolSize: 10, itemStyle: { color: colors[0], opacity: 0.8 }, emphasis: { scale: true, itemStyle: { shadowBlur: 12, shadowColor: hexToRgba(colors[0], 0.5) } } }],
        ...animationConfig,
      };
    }

    case 'bubble': {
      const bData = (datasets[0]?.data || []).map((v, i) => [v, datasets[1]?.data[i] ?? 0, Math.abs(datasets[2]?.data[i] ?? v)]);
      const maxR = Math.max(...bData.map(d => d[2]));
      const xLabel = datasets[0]?.label || 'X';
      const yLabel = datasets[1]?.label || 'Y';
      const sizeLabel = datasets[2]?.label || 'Size';
      return {
        color: colors,
        title: chartTitle('Bubble Chart', `${xLabel} vs ${yLabel}, sized by ${sizeLabel}`),
        tooltip: { ...ECHARTS_TOOLTIP_STYLE, trigger: 'item', formatter: p => `<b>${labels[p.dataIndex]}</b><br/>${xLabel}: ${fmtFull(p.value[0])}<br/>${yLabel}: ${fmtFull(p.value[1])}<br/>${sizeLabel}: ${fmtFull(p.value[2])}` },
        legend: { show: false }, toolbox,
        grid: { left: 60, right: 30, top: 56, bottom: 60, containLabel: true },
        xAxis: { type: 'value', name: xLabel, ...ECHARTS_AXIS_STYLE, axisLabel: { ...ECHARTS_AXIS_STYLE.axisLabel, formatter: v => fmt(v) }, nameLocation: 'middle', nameGap: 35, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        yAxis: { type: 'value', name: yLabel, ...ECHARTS_AXIS_STYLE, axisLabel: { ...ECHARTS_AXIS_STYLE.axisLabel, formatter: v => fmt(v) }, nameLocation: 'middle', nameGap: 50, nameTextStyle: { color: '#6b7280', fontSize: 11 } },
        series: [{ type: 'scatter', data: bData, symbolSize: d => Math.max(8, Math.sqrt(d[2] / maxR) * 60), itemStyle: { color: colors[0], opacity: 0.7 }, emphasis: { scale: true } }],
        ...animationConfig,
      };
    }

    case 'radar': {
      const radarLabels = labels.slice(0, 8);
      const maxVals = radarLabels.map((_, i) => Math.max(...datasets.map(d => Math.abs(d.data[i] ?? 0))) * 1.2);
      return {
        color: colors,
        title: chartTitle('Radar Chart', `Multi-dimensional profile`),
        tooltip: { ...ECHARTS_TOOLTIP_STYLE, trigger: 'item' },
        legend: showLegend ? legend : { show: false }, toolbox,
        radar: {
          indicator: radarLabels.map((l, i) => ({ name: l, max: maxVals[i] || 1 })),
          center: ['50%', '56%'],
          radius: '65%',
          axisNameGap: 8,
          axisName: { color: '#9ca3af', fontSize: 11 },
          splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
          splitArea: { areaStyle: { color: ['rgba(255,255,255,0.01)', 'rgba(255,255,255,0.03)'] } },
          axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
        },
        series: datasets.slice(0, 4).map((ds, i) => ({
          name: ds.label, type: 'radar',
          data: [{ value: ds.data.slice(0, 8), name: ds.label }],
          symbol: 'circle', symbolSize: 4,
          lineStyle: { width: 2, color: colors[i] },
          areaStyle: { color: hexToRgba(colors[i], 0.15) },
          itemStyle: { color: colors[i] },
        })),
        ...animationConfig,
      };
    }

    case 'heatmap': {
      const hmData = [];
      for (let r = 0; r < Math.min(datasets.length, 20); r++) {
        for (let c = 0; c < Math.min(labels.length, 20); c++) {
          hmData.push([c, r, datasets[r]?.data[c] ?? 0]);
        }
      }
      const vals = hmData.map(d => d[2]);
      return {
        title: chartTitle('Heatmap', `Cross-comparison matrix`),
        tooltip: { ...ECHARTS_TOOLTIP_STYLE, trigger: 'item', formatter: p => `${labels[p.value[0]]} × ${datasets[p.value[1]]?.label}<br/>${fmtFull(p.value[2])}` },
        toolbox,
        grid: { left: 80, right: 16, top: 56, bottom: 80, containLabel: true },
        xAxis: { type: 'category', data: labels.slice(0, 20), ...ECHARTS_AXIS_STYLE, axisLabel: { ...ECHARTS_AXIS_STYLE.axisLabel, rotate: 35 } },
        yAxis: { type: 'category', data: datasets.slice(0, 20).map(d => d.label), ...ECHARTS_AXIS_STYLE },
        visualMap: { min: Math.min(...vals), max: Math.max(...vals), calculable: true, orient: 'horizontal', left: 'center', bottom: 4, inRange: { color: ['#1f2937', '#3b82f6'] }, textStyle: { color: '#6b7280' } },
        series: [{ type: 'heatmap', data: hmData, label: { show: false }, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(59,130,246,0.3)' } } }],
        ...animationConfig,
      };
    }

    case 'funnel': {
      const fnData = labels.map((l, i) => ({ name: l, value: Math.abs(datasets[0]?.data[i] ?? 0) }))
        .sort((a, b) => b.value - a.value);
      return {
        color: colors,
        title: chartTitle('Funnel Chart', `${primaryMetric} — staged flow`),
        tooltip: { ...ECHARTS_TOOLTIP_STYLE, trigger: 'item', formatter: p => `${p.name}: ${fmtFull(p.value)} (${p.percent}%)` },
        toolbox,
        series: [{
          name: datasets[0]?.label || 'Value', type: 'funnel', data: fnData,
          left: '10%', width: '80%', top: 56, bottom: 20,
          label: { show: true, position: 'inside', color: '#09090b', fontWeight: 600, fontSize: 11, formatter: p => `${p.name}\n${fmt(p.value)}` },
          emphasis: { label: { fontSize: 13 } },
          itemStyle: { borderColor: '#09090b', borderWidth: 2 },
        }],
        ...animationConfig,
      };
    }

    case 'waterfall': {
      const wfData = datasets[0]?.data ?? [];
      let running = 0;
      const wfSeries = wfData.map((v, i) => {
        const val = Number(v) || 0;
        const prev = running;
        running += val;
        return { name: labels[i], start: prev, end: running, value: val, isPos: val >= 0 };
      });
      return {
        color: colors,
        title: chartTitle('Waterfall Chart', `Incremental changes in ${primaryMetric}`),
        tooltip: { ...ECHARTS_TOOLTIP_STYLE, trigger: 'axis', formatter: params => params.filter(p => p.seriesName !== 'base').map(p => `${p.seriesName}: ${fmtFull(p.value)}`).join('<br/>') },
        legend: { show: false }, toolbox,
        grid: baseGrid(labels.length > 8 ? 80 : 60),
        xAxis: xAxis(labels),
        yAxis: yAxis(),
        series: [
          { name: 'base', type: 'bar', stack: 'wf', data: wfSeries.map(d => d.start), itemStyle: { color: 'transparent' }, silent: true },
          { name: 'change', type: 'bar', stack: 'wf', data: wfSeries.map(d => Math.abs(d.value)), barMaxWidth: 48, itemStyle: { color: p => wfSeries[p.dataIndex]?.isPos ? colors[0] : colors[5], borderRadius: [4, 4, 0, 0] }, emphasis: { itemStyle: { shadowBlur: 8 } } },
        ],
        ...animationConfig,
      };
    }

    case 'gauge': {
      const gVal = Number(datasets[0]?.data[0]) || 0;
      const maxVal = Math.max(...(datasets[0]?.data || [gVal]).map(Number)) * 1.2 || 100;
      return {
        title: chartTitle('Gauge', labels[0] || primaryMetric),
        tooltip: { ...ECHARTS_TOOLTIP_STYLE, trigger: 'item', formatter: p => `${p.seriesName}: ${fmtFull(p.value)}` },
        toolbox,
        series: [{
          name: datasets[0]?.label || 'Value', type: 'gauge', min: 0, max: maxVal,
          radius: '75%',
          center: ['50%', '58%'],
          data: [{ value: gVal, name: labels[0] || 'Value' }],
          axisLine: { lineStyle: { width: 18, color: [[0.3, '#f87171'], [0.7, '#f59e0b'], [1, '#3b82f6']] } },
          pointer: { itemStyle: { color: '#f2f2ee' } },
          axisTick: { show: false }, splitLine: { show: false },
          axisLabel: { color: '#6b7280', fontSize: 10, formatter: v => fmt(v) },
          title: { color: '#9ca3af', fontSize: 12, offsetCenter: [0, '80%'] },
          detail: { valueAnimation: true, formatter: v => fmt(v), color: '#f2f2ee', fontSize: 28, fontWeight: 700, offsetCenter: [0, '50%'] },
        }],
        ...animationConfig,
      };
    }

    default:
      // Return null for unknown types so UI can handle it gracefully
      return null;
  }
}

/** Prepare labels and datasets from raw result */
export function prepareChartData(result) {
  const { columns = [], rows = [] } = result || {};
  if (!columns.length || !rows.length) return null;

  const numericCols = columns.filter(c =>
    rows.some(r => r[c] != null && r[c] !== '' && !Number.isNaN(Number(r[c]))),
  );
  const labelCols = columns.filter(c => !numericCols.includes(c));
  const labelCol = labelCols[0] || columns[0];

  if (!numericCols.length) return null;

  const TIME_PATTERN = /^\d{4}[-/]|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/i;
  const DATE_COL_NAMES = /date|month|year|week|quarter|period|time|day/i;
  const isTime =
    rows.some(r => TIME_PATTERN.test(String(r[labelCol] ?? ''))) ||
    columns.some(c => DATE_COL_NAMES.test(c));

  let displayRows = isTime
    ? [...rows].sort((a, b) => String(a[labelCol]).localeCompare(String(b[labelCol])))
    : [...rows].sort((a, b) => Number(b[numericCols[0]]) - Number(a[numericCols[0]]));

  const labels = displayRows.map(r => String(r[labelCol] ?? ''));
  const datasets = numericCols.map(col => ({
    label: col.replace(/_/g, ' '),
    originalColumn: col,
    data: displayRows.map(r => Number(r[col]) || 0),
  }));

  return { labels, datasets, isTime, labelCol: labelCol.replace(/_/g, ' '), numericCols };
}
