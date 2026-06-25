/**
 * biPalette.js
 * Professional BI color palette — consistent, no random assignment.
 * Inspired by Power BI / Fabric default theme with a lime accent overlay.
 */

export const BI_COLORS = [
  '#c8ff4d', // lime accent (primary)
  '#5eead4', // teal
  '#60a5fa', // blue
  '#f59e0b', // amber
  '#a78bfa', // violet
  '#f87171', // red
  '#34d399', // emerald
  '#fb923c', // orange
  '#38bdf8', // sky
  '#e879f9', // fuchsia
  '#4ade80', // green
  '#facc15', // yellow
];

export const BI_COLORS_MUTED = BI_COLORS.map(c => c + '55'); // 33% opacity hex
export const BI_COLORS_BORDER = BI_COLORS.map(c => c + 'cc'); // 80% opacity

/** Get color by index (wraps around) */
export function getColor(index, opacity = 1) {
  const hex = BI_COLORS[index % BI_COLORS.length];
  if (opacity === 1) return hex;
  return hexToRgba(hex, opacity);
}

export function hexToRgba(hex, alpha = 1) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/** Generate an array of colors for N series */
export function getPalette(count) {
  return Array.from({ length: count }, (_, i) => BI_COLORS[i % BI_COLORS.length]);
}

/** ECharts-compatible rich tooltip theme */
export const ECHARTS_TOOLTIP_STYLE = {
  backgroundColor: 'rgba(13,13,11,0.96)',
  borderColor: 'rgba(200,255,77,0.25)',
  borderWidth: 1,
  textStyle: { color: '#f2f2ee', fontSize: 12, fontFamily: 'Inter, system-ui, sans-serif' },
  padding: [10, 14],
  extraCssText: 'box-shadow: 0 8px 32px rgba(0,0,0,0.5); border-radius: 6px;',
};

export const ECHARTS_AXIS_STYLE = {
  axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
  axisTick: { show: false },
  axisLabel: { color: '#9ca3af', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' },
  splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)', type: 'dashed' } },
  nameTextStyle: { color: '#6b7280', fontSize: 11 },
};

export const ECHARTS_LEGEND_STYLE = {
  textStyle: { color: '#9ca3af', fontSize: 11, fontFamily: 'Inter, system-ui, sans-serif' },
  itemWidth: 10,
  itemHeight: 10,
  icon: 'roundRect',
  pageTextStyle: { color: '#9ca3af' },
};
