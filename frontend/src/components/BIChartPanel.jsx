import { useState, useMemo, useCallback, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import { recommendChartType, CHART_TYPE_GROUPS, ALL_CHART_TYPES } from '../utils/chartRecommender';
import { buildEChartsOption, prepareChartData } from '../utils/echartsBuilder';
import { analyzeResult, formatStatValue } from '../utils/resultAnalytics';

// Icon map using Unicode symbols (no extra icon lib needed beyond react-icons which is already installed)
const TYPE_ICONS = {
  bar: '⬛', horizontalBar: '▬', groupedBar: '⊞', stackedBar: '⊟',
  line: '〰', multiLine: '≋', area: '◿', stackedArea: '◸',
  donut: '◎', pie: '⬤', treemap: '⊡', funnel: '▽',
  scatter: '⠿', bubble: '⊚', radar: '⬡', heatmap: '⊞',
  waterfall: '⊓', gauge: '◉', kpiCard: '◈',
};

const SORT_OPTIONS = ['default', 'asc', 'desc', 'top10', 'bottom10'];

export default function BIChartPanel({ result, intent, query = '' }) {
  const chartData = useMemo(() => prepareChartData(result), [result]);
  const recommendation = useMemo(
    () => recommendChartType(result, intent, query),
    [result, intent, query],
  );

  const [activeType, setActiveType] = useState(null);
  const [sortMode, setSortMode] = useState('default');
  const [showLabels, setShowLabels] = useState(false);
  const [normalize, setNormalize] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [activeGroup, setActiveGroup] = useState(null); // toolbar group expand
  const [drillPath, setDrillPath] = useState([]); // breadcrumb drill state
  const [crossFilter, setCrossFilter] = useState(null);
  const chartRef = useRef(null);
  const containerRef = useRef(null);

  const effectiveType = activeType || recommendation.type;

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

    return { labels, datasets };
  }, [chartData, sortMode, normalize]);

  const echartsOption = useMemo(() => {
    if (!processedData) return null;
    if (effectiveType === 'kpiCard') return null;
    return buildEChartsOption(effectiveType, processedData.labels, processedData.datasets, { showLabels });
  }, [processedData, effectiveType, showLabels]);

  const analysis = useMemo(() => analyzeResult(result), [result]);

  const handleChartClick = useCallback((params) => {
    if (!params?.name) return;
    setCrossFilter(prev => prev === params.name ? null : params.name);
  }, []);

  const handleDrillDown = useCallback((label) => {
    setDrillPath(prev => [...prev, label]);
  }, []);

  const handleDrillUp = useCallback(() => {
    setDrillPath(prev => prev.slice(0, -1));
  }, []);

  const exportPng = useCallback(() => {
    const chart = chartRef.current?.getEchartsInstance();
    if (!chart) return;
    const url = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#0a0a08' });
    const a = document.createElement('a');
    a.href = url;
    a.download = 'chart.png';
    a.click();
  }, []);

  const exportSvg = useCallback(() => {
    const chart = chartRef.current?.getEchartsInstance();
    if (!chart) return;
    const url = chart.getDataURL({ type: 'svg' });
    const blob = new Blob([url], { type: 'image/svg+xml' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'chart.svg';
    a.click();
    URL.revokeObjectURL(a.href);
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
    setCrossFilter(null);
    setDrillPath([]);
    const chart = chartRef.current?.getEchartsInstance();
    chart?.dispatchAction({ type: 'restore' });
  }, []);

  if (!chartData || !processedData) return <EmptyState />;

  const chartHeight = isFullscreen ? '100%' : 420;

  return (
    <div ref={containerRef} className={`bi-chart-panel ${isFullscreen ? 'bi-chart-fullscreen' : ''}`}>
      {/* Header */}
      <div className="bi-chart-header">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] font-mono uppercase tracking-widest text-gray-500">Visualization</span>
          <span className="text-[10px] px-2 py-0.5 rounded bg-[#c8ff4d]/10 text-[#c8ff4d] border border-[#c8ff4d]/20">
            {ALL_CHART_TYPES.find(t => t.id === effectiveType)?.label || effectiveType}
          </span>
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
          >↑A</ControlBtn>
          <ControlBtn
            active={sortMode === 'desc'}
            onClick={() => setSortMode(s => s === 'desc' ? 'default' : 'desc')}
            title="Sort Descending"
          >↓Z</ControlBtn>
          <ControlBtn
            active={sortMode === 'top10'}
            onClick={() => setSortMode(s => s === 'top10' ? 'default' : 'top10')}
            title="Top 10"
          >T10</ControlBtn>
          <ControlBtn
            active={sortMode === 'bottom10'}
            onClick={() => setSortMode(s => s === 'bottom10' ? 'default' : 'bottom10')}
            title="Bottom 10"
          >B10</ControlBtn>
          <div className="bi-sep" />
          <ControlBtn active={showLabels} onClick={() => setShowLabels(v => !v)} title="Toggle Labels">
            Lbl
          </ControlBtn>
          <ControlBtn active={normalize} onClick={() => setNormalize(v => !v)} title="Normalize to %">
            %
          </ControlBtn>
          <div className="bi-sep" />
          <ControlBtn onClick={exportPng} title="Download PNG">PNG</ControlBtn>
          <ControlBtn onClick={exportSvg} title="Download SVG">SVG</ControlBtn>
          <ControlBtn onClick={toggleFullscreen} title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}>
            {isFullscreen ? '⊡' : '⊞'}
          </ControlBtn>
          <ControlBtn onClick={resetChart} title="Reset Chart">↺</ControlBtn>
        </div>
      </div>

      {/* Chart Type Toolbar */}
      <div className="bi-toolbar">
        {CHART_TYPE_GROUPS.map(group => (
          <div key={group.label} className="bi-toolbar-group">
            <button
              className="bi-toolbar-group-label"
              onClick={() => setActiveGroup(g => g === group.label ? null : group.label)}
            >
              {group.label} <span>{activeGroup === group.label ? '▲' : '▼'}</span>
            </button>
            {/* Always show active type from this group, expand on click */}
            <div className={`bi-toolbar-types ${activeGroup === group.label ? 'expanded' : ''}`}>
              {(activeGroup === group.label ? group.types : group.types.filter(t => t.id === effectiveType)).map(ct => (
                <button
                  key={ct.id}
                  title={ct.label}
                  onClick={() => { setActiveType(ct.id); setActiveGroup(null); }}
                  className={`bi-chart-type-btn ${effectiveType === ct.id ? 'active' : ''}`}
                >
                  <span className="bi-type-icon">{TYPE_ICONS[ct.id] || '▪'}</span>
                  <span className="bi-type-label">{ct.label}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
        {activeType && (
          <button className="bi-type-reset" onClick={() => { setActiveType(null); setActiveGroup(null); }} title="Reset to auto-recommended">
            Auto
          </button>
        )}
      </div>

      {/* Drill Breadcrumb */}
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

      {/* Cross-filter badge */}
      {crossFilter && (
        <div className="bi-crossfilter-badge">
          <span>Filtered: <strong>{crossFilter}</strong></span>
          <button onClick={() => setCrossFilter(null)}>✕</button>
        </div>
      )}

      {/* Chart Area */}
      <div className="bi-chart-area" style={{ height: chartHeight }}>
        {echartsOption ? (
          <ReactECharts
            ref={chartRef}
            option={echartsOption}
            style={{ width: '100%', height: '100%' }}
            onEvents={{ click: handleChartClick, dblclick: () => { setCrossFilter(null); setDrillPath([]); } }}
            notMerge={false}
            lazyUpdate={false}
            theme="dark"
          />
        ) : (
          effectiveType === 'kpiCard' && <KpiCardFallback analysis={analysis} />
        )}
      </div>

      {/* Summary stats footer */}
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

function ControlBtn({ children, onClick, active, title }) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`bi-control-btn ${active ? 'active' : ''}`}
    >
      {children}
    </button>
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
