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

/** Whether the app's dark theme is currently active (see index.css `[data-theme="dark"]`). */
export function isDarkTheme() {
  return typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme') === 'dark';
}

/** Main body/ink text color, theme-aware — for chart titles, tooltip values, gauge readouts. */
export function themeInk() {
  return isDarkTheme() ? '#F3ECE0' : '#1B2430';
}

/** Muted secondary text color, theme-aware — axis names, subtext, tooltip labels. */
export function themeMuted() {
  return isDarkTheme() ? '#B9AE9D' : '#8A8272';
}

/** Hairline border/gridline color as rgba, theme-aware (inverts base so it stays subtle on either background). */
export function themeLineRgba(alpha = 0.1) {
  return isDarkTheme() ? `rgba(243,236,224,${alpha})` : `rgba(27,36,48,${alpha})`;
}

/** ECharts-compatible rich tooltip theme, computed fresh so it follows the current light/dark theme. */
export function ECHARTS_TOOLTIP_STYLE() {
  const dark = isDarkTheme();
  return {
    backgroundColor: dark ? 'rgba(44,38,32,0.98)' : 'rgba(255,255,255,0.98)',
    borderColor: dark ? '#463C30' : '#DCD4C4',
    borderWidth: 1,
    textStyle: { color: themeInk(), fontSize: 12, fontFamily: 'Inter, system-ui, sans-serif' },
    padding: [10, 14],
    extraCssText: `box-shadow: 0 10px 25px -5px ${themeLineRgba(0.15)}; border-radius: 8px;`,
  };
}

export function ECHARTS_AXIS_STYLE() {
  return {
    axisLine: { lineStyle: { color: themeLineRgba(0.12) } },
    axisTick: { show: false },
    axisLabel: { color: '#9C7A3E', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' },
    splitLine: { lineStyle: { color: themeLineRgba(0.06), type: 'dashed' } },
    nameTextStyle: { color: themeMuted(), fontSize: 11 },
  };
}

export function ECHARTS_LEGEND_STYLE() {
  return {
    textStyle: { color: '#9C7A3E', fontSize: 11, fontFamily: 'Inter, system-ui, sans-serif' },
    itemWidth: 10,
    itemHeight: 10,
    icon: 'roundRect',
    pageTextStyle: { color: '#9C7A3E' },
  };
}
