/**
 * biPalette.js
 * Warm, classy BI color palette — consistent, no random assignment.
 * A clay/terracotta primary with a curated set of muted, harmonious hues.
 */

export const BI_COLORS = [
  '#9C4A2A', // clay (primary)
  '#5B7FA6', // dusty blue
  '#6B8F71', // sage
  '#C9A227', // muted gold
  '#A65B6B', // dusty rose
  '#4FA095', // teal
  '#B8763F', // amber-brown
  '#8C6BAE', // muted plum
  '#7A8B4A', // olive
  '#C97F9A', // dusty pink
  '#4A6B8A', // slate blue
  '#D4A24E', // honey
];

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
  backgroundColor: 'rgba(255,255,255,0.98)',
  borderColor: '#DCD4C4',
  borderWidth: 1,
  textStyle: { color: '#1B2430', fontSize: 12, fontFamily: 'Inter, system-ui, sans-serif' },
  padding: [10, 14],
  extraCssText: 'box-shadow: 0 10px 25px -5px rgba(27,36,48,0.15); border-radius: 8px;',
};

export const ECHARTS_AXIS_STYLE = {
  axisLine: { lineStyle: { color: 'rgba(27,36,48,0.12)' } },
  axisTick: { show: false },
  axisLabel: { color: '#9C7A3E', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' },
  splitLine: { lineStyle: { color: 'rgba(27,36,48,0.06)', type: 'dashed' } },
  nameTextStyle: { color: '#8A8272', fontSize: 11 },
};

export const ECHARTS_LEGEND_STYLE = {
  textStyle: { color: '#9C7A3E', fontSize: 11, fontFamily: 'Inter, system-ui, sans-serif' },
  itemWidth: 10,
  itemHeight: 10,
  icon: 'roundRect',
  pageTextStyle: { color: '#9C7A3E' },
};
