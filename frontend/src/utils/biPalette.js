/**
 * biPalette.js
 * Professional BI color palette — consistent, no random assignment.
 * Modern enterprise aesthetic (blues, purples, teals, and complementary colors).
 */

export const BI_COLORS = [
  '#3b82f6', // blue-500 (primary)
  '#8b5cf6', // violet-500
  '#10b981', // emerald-500
  '#f59e0b', // amber-500
  '#0ea5e9', // sky-500
  '#ec4899', // pink-500
  '#14b8a6', // teal-500
  '#f43f5e', // rose-500
  '#6366f1', // indigo-500
  '#84cc16', // lime-500
  '#a855f7', // purple-500
  '#eab308', // yellow-500
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
  backgroundColor: 'rgba(24,24,27,0.96)', /* zinc-900 */
  borderColor: 'rgba(59,130,246,0.3)',    /* blue-500 */
  borderWidth: 1,
  textStyle: { color: '#f4f4f5', fontSize: 12, fontFamily: 'Inter, system-ui, sans-serif' },
  padding: [10, 14],
  extraCssText: 'box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5); border-radius: 8px;',
};

export const ECHARTS_AXIS_STYLE = {
  axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
  axisTick: { show: false },
  axisLabel: { color: '#a1a1aa', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' },
  splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)', type: 'dashed' } },
  nameTextStyle: { color: '#71717a', fontSize: 11 },
};

export const ECHARTS_LEGEND_STYLE = {
  textStyle: { color: '#a1a1aa', fontSize: 11, fontFamily: 'Inter, system-ui, sans-serif' },
  itemWidth: 10,
  itemHeight: 10,
  icon: 'roundRect',
  pageTextStyle: { color: '#a1a1aa' },
};
