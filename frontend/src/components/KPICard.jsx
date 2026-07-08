import { useMemo, useEffect, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { analyzeResult, formatStatValue, periodComparison } from '../utils/resultAnalytics';
import { hexToRgba, BI_COLORS } from '../utils/biPalette';

/* eslint-disable react-refresh/only-export-components */
export function detectKpiMetrics(result) {
  if (!result?.rows?.length || !result?.columns?.length) return null;
  const { columns, rows } = result;

  if (rows.length === 1) {
    const kpis = columns
      .filter(c => rows[0][c] != null && !Number.isNaN(Number(rows[0][c])))
      .map(c => ({ label: c.replace(/_/g, ' '), value: Number(rows[0][c]), raw: rows[0][c] }));
    if (kpis.length >= 1 && kpis.length <= 8) return kpis;
  }
  if (rows.length <= 3 && columns.length === 2) {
    const numericCol = columns.find(c => rows.every(r => !Number.isNaN(Number(r[c]))));
    const labelCol = columns.find(c => c !== numericCol);
    if (numericCol && labelCol && rows.length === 1) {
      return [{ label: String(rows[0][labelCol]), value: Number(rows[0][numericCol]), raw: rows[0][numericCol] }];
    }
  }
  return null;
}

function formatKpiValue(value) {
  if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (Math.abs(value) >= 1e4) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (Number.isInteger(value)) return value.toLocaleString();
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function detectUnit(label) {
  const l = label.toLowerCase();
  if (l.includes('revenue') || l.includes('sales') || l.includes('profit') || l.includes('amount') || l.includes('price') || l.includes('cost') || l.includes('income') || l.includes('earning')) return '$';
  if (l.includes('rate') || l.includes('percent') || l.includes('ratio') || l.includes('margin')) return '%';
  return '';
}

/** Animated count-up hook */
function useCountUp(target, duration = 800) {
  const [value, setValue] = useState(0);
  const rafRef = useRef(null);
  useEffect(() => {
    const start = Date.now();
    const startVal = 0;
    const step = () => {
      const elapsed = Date.now() - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setValue(startVal + (target - startVal) * eased);
      if (progress < 1) rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);
  return value;
}

/** Mini sparkline using ECharts */
function MiniSparkline({ data, color }) {
  const option = useMemo(() => ({
    animation: true, animationDuration: 800,
    grid: { left: 0, right: 0, top: 2, bottom: 2 },
    xAxis: { type: 'category', show: false },
    yAxis: { type: 'value', show: false },
    series: [{
      type: 'line', data, smooth: 0.4, symbol: 'none',
      lineStyle: { width: 1.5, color },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: hexToRgba(color, 0.4) }, { offset: 1, color: hexToRgba(color, 0) }] } },
    }],
  }), [data, color]);

  return (
    <ReactECharts
      option={option}
      style={{ width: '100%', height: 40 }}
      opts={{ renderer: 'canvas' }}
    />
  );
}

/** Single animated KPI card */
function KPICardItem({ kpi, index, trend, sparkData, isTop, isBottom }) {
  const animValue = useCountUp(kpi.value, 900 + index * 120);
  const unit = detectUnit(kpi.label);
  const color = BI_COLORS[index % BI_COLORS.length];
  const trendDir = trend?.direction;

  return (
    <div className="kpi-card" style={{ '--kpi-accent': color }}>
      <div className="kpi-card-inner">
        <div className="kpi-card-top">
          <p className="kpi-label">{kpi.label}</p>
          <div className="kpi-badges">
            {isTop && <span className="kpi-badge top">🏆 Top</span>}
            {isBottom && <span className="kpi-badge bottom">⚠ Low</span>}
          </div>
        </div>
        <div className="kpi-value-row">
          {unit === '$' && <span className="kpi-unit">$</span>}
          <span className="kpi-value">{formatKpiValue(animValue)}</span>
          {unit === '%' && <span className="kpi-unit kpi-unit-suffix">%</span>}
        </div>
        {trendDir && trendDir !== 'flat' && (
          <div className={`kpi-trend ${trendDir}`}>
            <span className="kpi-trend-arrow">{trendDir === 'up' ? '↑' : '↓'}</span>
            <span className="kpi-trend-pct">
              {trend.pct != null ? `${Math.abs(trend.pct).toFixed(1)}% vs prev` : trendDir}
            </span>
          </div>
        )}
        {sparkData && sparkData.length > 1 && (
          <div className="kpi-spark">
            <MiniSparkline data={sparkData} color={color} />
          </div>
        )}
        <div className="kpi-glow" style={{ background: hexToRgba(color, 0.08) }} />
      </div>
    </div>
  );
}

export default function KPICard({ result, intent = '', query = '' }) {
  const kpis = detectKpiMetrics(result);
  const analysis = useMemo(() => analyzeResult(result, intent, query), [result, intent, query]);
  const trend = useMemo(() => periodComparison(result), [result]);

  if (!kpis?.length) return null;

  // Generate sparkline data from stats if available
  const getSparkData = (kpi) => {
    if (!analysis?.numericStats) return null;
    const stat = analysis.numericStats.find(s => s.label === kpi.label);
    if (!stat) return null;
    // Generate a synthetic trend line from min→avg→max
    return [stat.min, (stat.min + stat.avg) / 2, stat.avg, (stat.avg + stat.max) / 2, stat.max];
  };

  const maxVal = Math.max(...kpis.map(k => k.value));
  const minVal = Math.min(...kpis.map(k => k.value));

  return (
    <div className="kpi-row">
      <div className="kpi-row-header">
        <h3 className="kpi-row-title">Key Metrics</h3>
        {trend && trend.pct != null && (
          <span className={`kpi-period-badge ${trend.direction}`}>
            Period: {trend.direction === 'up' ? '▲' : '▼'} {Math.abs(trend.pct).toFixed(1)}%
          </span>
        )}
      </div>
      <div className={`kpi-grid kpi-count-${Math.min(kpis.length, 6)}`}>
        {kpis.map((kpi, i) => (
          <KPICardItem
            key={kpi.label}
            kpi={kpi}
            index={i}
            trend={i === 0 ? trend : null}
            sparkData={getSparkData(kpi)}
            isTop={kpi.value === maxVal && kpis.length > 1}
            isBottom={kpi.value === minVal && kpis.length > 1}
          />
        ))}
      </div>
    </div>
  );
}
