import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';
import {
  TbChartBar, TbChartBarOff, TbChartLine, TbChartArea, TbChartDonut,
  TbChartPie, TbChartTreemap, TbChartScatter, TbChartRadar,
  TbChartArrows, TbChartBubble, TbChartCandle, TbChartDots,
  TbArrowBarUp, TbArrowBarDown, TbSortAscendingNumbers, TbSortDescendingNumbers,
  TbArrowsMaximize, TbArrowsMinimize, TbRefresh, TbDownload,
  TbEye, TbEyeOff, TbPercentage, TbDots, TbStar, TbX,
  TbAlertTriangle, TbLayoutGrid, TbFilter
} from 'react-icons/tb';
import { recommendChartType, getChartCompatibility, suggestAlternatives, CHART_TYPE_GROUPS, ALL_CHART_TYPES } from '../utils/chartRecommender';
import { buildEChartsOption, prepareChartData } from '../utils/echartsBuilder';
import { resolveVisualizationSpec } from '../utils/semanticClassifier';
import { analyzeResult, formatStatValue, periodComparison } from '../utils/resultAnalytics';
import { detectKpiMetrics } from './KPICard';
import { BI_COLORS } from '../utils/biPalette';

/* ═══════════════════════════════════════════════════════════
   ICON MAP — maps chart type id → react-icons component
═══════════════════════════════════════════════════════════ */
const TYPE_ICONS = {
  bar: TbChartBar,
  horizontalBar: TbArrowBarUp,
  groupedBar: TbChartBar,
  stackedBar: TbChartBar,
  line: TbChartLine,
  multiLine: TbChartLine,
  area: TbChartArea,
  stackedArea: TbChartArea,
  cumulative: TbChartArrows,
  donut: TbChartDonut,
  pie: TbChartPie,
  treemap: TbChartTreemap,
  funnel: TbFilter,
  scatter: TbChartScatter,
  bubble: TbChartBubble,
  radar: TbChartRadar,
  heatmap: TbLayoutGrid,
  waterfall: TbChartCandle,
  gauge: TbChartDots,
  kpiCard: TbStar,
};

/* Primary chart types shown directly in the toolbar */
const PRIMARY_TYPES = ['bar', 'horizontalBar', 'line', 'area', 'cumulative', 'donut', 'pie', 'treemap'];
/* Advanced chart types hidden behind "More" menu */
const ADVANCED_TYPES = ['groupedBar', 'stackedBar', 'multiLine', 'stackedArea', 'funnel', 'scatter', 'bubble', 'radar', 'heatmap', 'waterfall', 'gauge'];

const TOP_N_OPTIONS = [
  { value: 0, label: 'All' },
  { value: 5, label: 'Top 5' },
  { value: 10, label: 'Top 10' },
  { value: 20, label: 'Top 20' },
];

export default function BIChartPanel({ result, intent, query = '' }) {
  const spec = useMemo(
    () => resolveVisualizationSpec(result, intent, query),
    [result, intent, query]
  );

  const semanticResult = useMemo(() => {
    if (!spec || !result) return result;
    const allowedColumns = [];
    if (spec.dimension) allowedColumns.push(spec.dimension);
    if (spec.secondaryDimension) allowedColumns.push(spec.secondaryDimension);
    if (spec.primaryMeasure) allowedColumns.push(spec.primaryMeasure);
    if (spec.secondaryMeasures) allowedColumns.push(...spec.secondaryMeasures);
    
    return {
      columns: allowedColumns,
      rows: result.rows
    };
  }, [spec, result]);

  const chartData = useMemo(() => prepareChartData(semanticResult, spec), [semanticResult, spec]);
  
  const recommendation = useMemo(
    () => ({ type: spec?.recommendedChart || 'bar' }),
    [spec]
  );
  
  const compatibility = useMemo(
    () => getChartCompatibility(semanticResult, intent, query),
    [semanticResult, intent, query],
  );

  const [activeType, setActiveType] = useState(null);
  const [sortMode, setSortMode] = useState('default');
  const [showLabels, setShowLabels] = useState(false);
  const [normalize, setNormalize] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showMore, setShowMore] = useState(false);
  const [topN, setTopN] = useState(0); // 0 means All
  const [drillPath, setDrillPath] = useState([]); // breadcrumb drill state
  const [crossFilter, setCrossFilter] = useState(null);
  const chartRef = useRef(null);
  const containerRef = useRef(null);
  const moreMenuRef = useRef(null);

  const effectiveType = activeType || recommendation.type;

  // Reset active type when result changes
  useEffect(() => {
    setActiveType(null);
    setSortMode('default');
    setShowLabels(false);
    setNormalize(false);
    setTopN(0);
    setCrossFilter(null);
    setDrillPath([]);
  }, [result]);

  // Close "More" menu on outside click
  useEffect(() => {
    const handler = (e) => {
      if (moreMenuRef.current && !moreMenuRef.current.contains(e.target)) {
        setShowMore(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Fullscreen change listener
  useEffect(() => {
    const handler = () => {
      if (!document.fullscreenElement) setIsFullscreen(false);
    };
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  // ResizeObserver for chart container
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => {
      const chart = chartRef.current?.getEchartsInstance?.();
      if (chart) chart.resize();
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const processedData = useMemo(() => {
    if (!chartData) return null;
    let { labels, datasets } = chartData;

    // Normalize
    if (normalize) {
      const totals = labels.map((_, i) => datasets.reduce((s, d) => s + (d.data[i] || 0), 0));
      datasets = datasets.map(ds => ({ ...ds, data: ds.data.map((v, i) => totals[i] ? (v / totals[i]) * 100 : 0) }));
    }

    // Sort
    if (sortMode !== 'default' && datasets[0]) {
      const paired = labels.map((l, i) => ({ l, vals: datasets.map(d => d.data[i]) }));
      if (sortMode === 'asc') paired.sort((a, b) => a.vals[0] - b.vals[0]);
      if (sortMode === 'desc') paired.sort((a, b) => b.vals[0] - a.vals[0]);
      if (sortMode === 'top10') paired.sort((a, b) => b.vals[0] - a.vals[0]).splice(10);
      if (sortMode === 'bottom10') paired.sort((a, b) => a.vals[0] - b.vals[0]).splice(10);
      labels = paired.map(p => p.l);
      datasets = datasets.map((ds, di) => ({ ...ds, data: paired.map(p => p.vals[di]) }));
    }

    // Top N filter
    if (topN > 0 && labels.length > topN) {
      labels = labels.slice(0, topN);
      datasets = datasets.map(ds => ({ ...ds, data: ds.data.slice(0, topN) }));
    }

    return { labels, datasets };
  }, [chartData, sortMode, normalize, topN]);

  const echartsOption = useMemo(() => {
    if (!processedData) return null;
    if (effectiveType === 'kpiCard') return null;
    // Check compatibility — if disabled, return null so we show fallback
    if (compatibility[effectiveType] && !compatibility[effectiveType].enabled) return null;
    return buildEChartsOption(effectiveType, processedData.labels, processedData.datasets, {
      showLabels,
      labelCol: chartData?.labelCol,
    });
  }, [processedData, effectiveType, showLabels, compatibility, chartData?.labelCol]);

  const analysis = useMemo(() => analyzeResult(result), [result]);
  const kpis = useMemo(() => detectKpiMetrics(result), [result]);
  const kpiTrend = useMemo(() => periodComparison(result), [result]);

  const handleChartClick = useCallback((params) => {
    if (!params?.name) return;
    setCrossFilter(prev => prev === params.name ? null : params.name);
  }, []);

  const handleDrillUp = useCallback(() => {
    setDrillPath(prev => prev.slice(0, -1));
  }, []);

  const exportPng = useCallback(() => {
    const chart = chartRef.current?.getEchartsInstance();
    if (!chart) return;
    const url = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#FFFFFF' });
    const a = document.createElement('a');
    a.href = url;
    a.download = 'chart.png';
    a.click();
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen?.();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen?.();
      setIsFullscreen(false);
    }
  }, []);

  const resetChart = useCallback(() => {
    setActiveType(null);
    setSortMode('default');
    setShowLabels(false);
    setNormalize(false);
    setTopN(0);
    setCrossFilter(null);
    setDrillPath([]);
    const chart = chartRef.current?.getEchartsInstance();
    chart?.dispatchAction({ type: 'restore' });
  }, []);

  const handleTypeSelect = useCallback((typeId) => {
    setActiveType(typeId);
    setShowMore(false);
  }, []);

  if (!chartData || !processedData) return <EmptyState />;

  const chartHeight = isFullscreen ? '100%' : 440;
  const isUnsupported = effectiveType !== 'kpiCard' && !echartsOption;
  const alternatives = isUnsupported ? suggestAlternatives(result, intent, query) : null;

  return (
    <div ref={containerRef} className={`bi-chart-panel ${isFullscreen ? 'bi-chart-fullscreen' : ''}`}>
      {/* ── Header ── */}
      <div className="bi-chart-header">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] font-mono uppercase tracking-widest text-[#9C7A3E]">Overview</span>
          <span className="text-[10px] px-2 py-0.5 rounded bg-[#9C4A2A]/10 text-[#9C4A2A] border border-[#9C4A2A]/20">
            {ALL_CHART_TYPES.find(t => t.id === effectiveType)?.label || effectiveType}
          </span>
          {compatibility[effectiveType]?.recommended && !activeType && (
            <span className="bi-recommended-badge">★ Recommended</span>
          )}
          {recommendation.confidence > 0 && !activeType && (
            <span className="text-[10px] text-gray-600 hidden sm:inline">
              Auto: {recommendation.reason}
            </span>
          )}
        </div>

        {/* Chart Controls Bar */}
        <div className="bi-controls-bar">
          <ControlBtn
            active={sortMode === 'asc'}
            onClick={() => setSortMode(s => s === 'asc' ? 'default' : 'asc')}
            title="Sort Ascending"
            icon={<TbSortAscendingNumbers size={13} />}
          />
          <ControlBtn
            active={sortMode === 'desc'}
            onClick={() => setSortMode(s => s === 'desc' ? 'default' : 'desc')}
            title="Sort Descending"
            icon={<TbSortDescendingNumbers size={13} />}
          />
          {/* Top N selector */}
          <div className="bi-topn-wrap">
            <select
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value))}
              className="bi-topn-select"
              title="Limit results shown"
            >
              {TOP_N_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="bi-sep" />
          <ControlBtn
            active={showLabels}
            onClick={() => setShowLabels(v => !v)}
            title="Toggle Data Labels"
            icon={showLabels ? <TbEye size={13} /> : <TbEyeOff size={13} />}
          />
          <ControlBtn
            active={normalize}
            onClick={() => setNormalize(v => !v)}
            title="Normalize to %"
            icon={<TbPercentage size={13} />}
          />
          <div className="bi-sep" />
          <ControlBtn onClick={exportPng} title="Download PNG" icon={<TbDownload size={13} />} />
          <ControlBtn
            onClick={toggleFullscreen}
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
            icon={isFullscreen ? <TbArrowsMinimize size={13} /> : <TbArrowsMaximize size={13} />}
          />
          <ControlBtn onClick={resetChart} title="Reset Chart" icon={<TbRefresh size={13} />} />
        </div>
      </div>

      {/* ── KPI Strip (inside this card, not separate cards) ── */}
      {kpis?.length > 0 && (
        <div className="kpi-strip">
          {kpis.slice(0, 4).map((kpi, i) => {
            const trend = i === 0 ? kpiTrend : null;
            const trendDir = trend?.direction;
            return (
              <div key={kpi.label} className="kpi-strip-cell" style={{ '--kpi-accent': BI_COLORS[i % BI_COLORS.length] }}>
                <p className="kpi-strip-label">{kpi.label}</p>
                <p className="kpi-strip-value">{formatStatValue(kpi.value)}</p>
                {trendDir && trendDir !== 'flat' && (
                  <div className={`kpi-strip-trend ${trendDir}`}>
                    <span>{trendDir === 'up' ? '▲' : '▼'}</span>
                    <span>{trend.pct != null ? `${Math.abs(trend.pct).toFixed(1)}%` : trendDir}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Chart Type Toolbar ── */}
      <div className="bi-chart-toolbar-wrap">
        <div className="bi-chart-toolbar-scroll">
          {PRIMARY_TYPES.map(typeId => {
            const ct = ALL_CHART_TYPES.find(t => t.id === typeId);
            if (!ct) return null;
            const compat = compatibility[typeId];
            const Icon = TYPE_ICONS[typeId] || TbChartBar;
            const isActive = effectiveType === typeId;
            const isRecommended = compat?.recommended;
            const isDisabled = compat && !compat.enabled;
            return (
              <button
                key={typeId}
                title={isDisabled ? `Not suitable for the current result data. ${compat.reason}` : ct.label}
                onClick={() => !isDisabled && handleTypeSelect(typeId)}
                className={`bi-chart-type-btn ${isActive ? 'active' : ''} ${isDisabled ? 'disabled' : ''} ${isRecommended ? 'recommended' : ''}`}
                disabled={isDisabled}
              >
                <Icon size={14} />
                <span className="bi-type-label">{ct.label}</span>
                {isRecommended && <span className="bi-rec-dot" title="Recommended for this data" />}
              </button>
            );
          })}
        </div>

        {/* More menu — sits outside the scrollable area */}
        <div className="bi-more-wrap" ref={moreMenuRef}>
          <button
            className={`bi-chart-type-btn ${showMore ? 'active' : ''} ${ADVANCED_TYPES.includes(effectiveType) ? 'has-active' : ''}`}
            onClick={() => setShowMore(v => !v)}
            title="More chart types"
          >
            <TbDots size={14} />
            <span className="bi-type-label">More</span>
          </button>
          {showMore && (
            <div className="bi-more-dropdown">
              <p className="bi-more-heading">Advanced Charts</p>
              {ADVANCED_TYPES.map(typeId => {
                const ct = ALL_CHART_TYPES.find(t => t.id === typeId);
                if (!ct) return null;
                const compat = compatibility[typeId];
                const Icon = TYPE_ICONS[typeId] || TbChartBar;
                const isActive = effectiveType === typeId;
                const isDisabled = compat && !compat.enabled;
                return (
                  <button
                    key={typeId}
                    title={isDisabled ? compat.reason : ct.label}
                    onClick={() => !isDisabled && handleTypeSelect(typeId)}
                    className={`bi-more-item ${isActive ? 'active' : ''} ${isDisabled ? 'disabled' : ''}`}
                    disabled={isDisabled}
                  >
                    <Icon size={14} />
                    <span>{ct.label}</span>
                    {isDisabled && <span className="bi-more-disabled-hint">—</span>}
                    {compat?.recommended && <span className="bi-more-rec">★</span>}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Auto reset button */}
        {activeType && (
          <button className="bi-type-reset" onClick={() => { setActiveType(null); setShowMore(false); }} title="Reset to auto-recommended">
            Auto
          </button>
        )}
      </div>

      {/* ── Drill Breadcrumb ── */}
      {drillPath.length > 0 && (
        <div className="bi-breadcrumb">
          <button onClick={() => setDrillPath([])} className="bi-breadcrumb-item">All</button>
          {drillPath.map((p, i) => (
            <span key={i} className="flex items-center gap-1">
              <span className="text-gray-600">›</span>
              <button onClick={() => setDrillPath(prev => prev.slice(0, i + 1))} className="bi-breadcrumb-item active">
                {p}
              </button>
            </span>
          ))}
          <button onClick={handleDrillUp} className="bi-breadcrumb-up">↑ Up</button>
        </div>
      )}

      {/* ── Cross-filter badge ── */}
      {crossFilter && (
        <div className="bi-crossfilter-badge">
          <span>Filtered: <strong>{crossFilter}</strong></span>
          <button onClick={() => setCrossFilter(null)}>✕</button>
        </div>
      )}

      {/* ── Chart Area ── */}
      <div className="bi-chart-area" style={{ height: chartHeight }}>
        {echartsOption ? (
          <ReactECharts
            key={effectiveType}
            ref={chartRef}
            option={echartsOption}
            style={{ width: '100%', height: '100%' }}
            onEvents={{ click: handleChartClick, dblclick: () => { setCrossFilter(null); setDrillPath([]); } }}
            notMerge={true}
            lazyUpdate={false}
          />
        ) : isUnsupported ? (
          <UnsupportedChart
            type={effectiveType}
            compatibility={compatibility}
            alternatives={alternatives}
            onSelectType={handleTypeSelect}
          />
        ) : (
          effectiveType === 'kpiCard' && <KpiCardFallback analysis={analysis} />
        )}
      </div>

      {/* ── Summary stats footer ── */}
      {analysis && (
        <div className="bi-chart-footer">
          {analysis.numericStats?.slice(0, 3).map(stat => (
            <div key={stat.column} className="bi-stat-chip">
              <span className="bi-stat-label">{stat.label}</span>
              <span className="bi-stat-val">Σ {formatStatValue(stat.sum)}</span>
              <span className="bi-stat-val">Avg {formatStatValue(stat.avg)}</span>
            </div>
          ))}
          {processedData.labels.length !== chartData?.labels?.length && (
            <span className="text-[10px] text-gray-600 ml-auto">
              Showing {processedData.labels.length} of {chartData.labels.length} items
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   SUB-COMPONENTS
═══════════════════════════════════════════════════════════ */

function ControlBtn({ children, onClick, active, title, icon }) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`bi-control-btn ${active ? 'active' : ''}`}
    >
      {icon || children}
    </button>
  );
}

function UnsupportedChart({ type, compatibility, alternatives, onSelectType }) {
  const typeMeta = ALL_CHART_TYPES.find(t => t.id === type);
  const reason = compatibility[type]?.reason || 'Not suitable for the current result data.';

  return (
    <div className="bi-unsupported-state">
      <div className="bi-unsupported-icon"><TbAlertTriangle size={36} /></div>
      <p className="bi-unsupported-title">
        {typeMeta?.label || type} is not suitable for this data
      </p>
      <p className="bi-unsupported-reason">{reason}</p>
      {alternatives && alternatives.alternatives.length > 0 && (
        <div className="bi-unsupported-alts">
          <p className="bi-unsupported-alt-label">Try instead:</p>
          <div className="bi-unsupported-alt-btns">
            {alternatives.alternatives.map(label => {
              const ct = ALL_CHART_TYPES.find(t => t.label === label);
              if (!ct) return null;
              const Icon = TYPE_ICONS[ct.id] || TbChartBar;
              return (
                <button
                  key={ct.id}
                  className="bi-unsupported-alt-btn"
                  onClick={() => onSelectType(ct.id)}
                >
                  <Icon size={14} />
                  {label}
                  {compatibility[ct.id]?.recommended && <span className="bi-rec-dot" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function KpiCardFallback({ analysis }) {
  if (!analysis?.numericStats?.length) return <EmptyState />;
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-4 p-4 h-full content-center">
      {analysis.numericStats.slice(0, 6).map((stat, i) => (
        <div key={stat.column} className={`bi-kpi-mini-card color-${i}`}>
          <p className="bi-kpi-mini-label">{stat.label}</p>
          <p className="bi-kpi-mini-value">{formatStatValue(stat.sum)}</p>
          <p className="bi-kpi-mini-sub">avg {formatStatValue(stat.avg)}</p>
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="bi-empty-state">
      <div className="bi-empty-icon">📊</div>
      <p className="bi-empty-title">No chart available</p>
      <p className="bi-empty-sub">The result doesn't have numeric data that can be visualized.</p>
    </div>
  );
}
