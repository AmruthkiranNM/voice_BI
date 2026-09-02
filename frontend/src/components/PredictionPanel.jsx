import { useMemo } from 'react';
import { TbAlertTriangle, TbShieldCheck, TbShieldOff, TbChartBar } from 'react-icons/tb';
import ReactECharts from 'echarts-for-react';

/**
 * PredictionPanel — Renders ML prediction results.
 *
 * Expects `result.prediction` and `result.visualization` from ml_agent.
 */
export default function PredictionPanel({ result, insight }) {
  const prediction = result?.prediction;
  const visualization = result?.visualization;
  const mode = visualization?.mode || 'single';
  const predictions = prediction?.predictions || [];
  const isForecast = mode === 'forecast';
  const firstPred = predictions[0] || (isForecast && prediction?.forecast?.[0]) || null;

  const accuracy = prediction?.model_accuracy;


  if (!firstPred) {
    return (
      <div className="panel-card text-center py-10 text-zinc-400">
        <TbAlertTriangle className="w-8 h-8 mx-auto mb-3 text-amber-400" />
        <p className="text-sm">{result?.error || 'No prediction result available.'}</p>
      </div>
    );
  }

  // Single mode (gauge & profile view)
  if (mode === 'single') {
    const probability = firstPred.probability;
    const riskLevel = firstPred.risk ?? 'Unknown';
    const featureImpacts = firstPred.feature_impacts || [];
    const rowData = firstPred.row_data || {};
    const isClassification = probability != null;
    const targetColumn = prediction?.target_column || 'Value';

    return (
      <div className="bi-dashboard animate-in space-y-6">
        {/* ── Main Prediction Display ──────────────────────────── */}
        <div className="panel-card flex flex-col items-center py-8 relative overflow-hidden">
          {isClassification ? (
            <>
              <div
                className="absolute inset-0 opacity-10 rounded-2xl"
                style={{
                  background: `radial-gradient(circle at 50% 40%, ${riskColor(riskLevel)}, transparent 70%)`,
                }}
              />
              <RiskIcon level={riskLevel} />
              <p className="text-5xl font-bold mt-4 font-mono" style={{ color: riskColor(riskLevel) }}>
                {(probability * 100).toFixed(1)}%
              </p>
              <p className="text-sm text-zinc-400 mt-1">Churn Probability</p>
              <span
                className="mt-3 px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider"
                style={{
                  backgroundColor: `${riskColor(riskLevel)}20`,
                  color: riskColor(riskLevel),
                }}
              >
                {riskLevel} Risk
              </span>
            </>
          ) : (
            <>
              <div
                className="absolute inset-0 opacity-10 rounded-2xl"
                style={{
                  background: `radial-gradient(circle at 50% 40%, #6366f1, transparent 70%)`,
                }}
              />
              <TbChartBar className="w-14 h-14 text-indigo-400" />
              <p className="text-5xl font-bold mt-4 font-mono text-indigo-400">
                {typeof firstPred.prediction === 'number' ? firstPred.prediction.toLocaleString(undefined, { maximumFractionDigits: 2 }) : firstPred.prediction}
              </p>
              <p className="text-sm text-zinc-400 mt-1">Predicted {targetColumn.replace(/_/g, ' ')}</p>
            </>
          )}
          {accuracy != null && (
            <p className="text-[11px] text-zinc-500 mt-3">
              {isClassification ? 'Model accuracy' : 'R² Score'}: <span className="font-mono text-zinc-400">{typeof accuracy === 'number' ? (accuracy * 100).toFixed(1) + '%' : accuracy}</span>
            </p>
          )}
        </div>

        {/* ── Two-column layout ──────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Feature Impacts */}
          <div className="panel-card">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-4 flex items-center gap-2">
              <TbChartBar className="w-4 h-4" /> Key Factors
            </h3>
            <div className="space-y-3">
              {featureImpacts.map((fi, i) => {
                const maxImportance = featureImpacts[0]?.importance || 1;
                const barWidth = Math.max(5, (fi.importance / maxImportance) * 100);
                return (
                  <div key={i}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-zinc-300 capitalize">{fi.feature}</span>
                      <span className="text-xs text-zinc-500 font-mono">{fi.value}</span>
                    </div>
                    <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                          width: `${barWidth}%`,
                          background: `linear-gradient(90deg, ${riskColor(riskLevel)}88, ${riskColor(riskLevel)})`,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Customer Details */}
          <div className="panel-card">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-4">
              Customer Profile
            </h3>
            <div className="space-y-2">
              {Object.entries(rowData)
                .filter(([k]) => !['surname', 'rownumber', 'row_number'].includes(k.toLowerCase()))
                .slice(0, 12)
                .map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between py-1 border-b border-zinc-800/50">
                    <span className="text-sm text-zinc-400 capitalize">{key.replace(/_/g, ' ')}</span>
                    <span className="text-sm text-zinc-200 font-mono">{formatValue(value)}</span>
                  </div>
                ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Batch mode (multi-chart dashboard)
  const charts = visualization?.charts || [];
  
  return (
    <div className="bi-dashboard animate-in space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {charts.map((chart, idx) => (
          <div key={idx} className="panel-card flex flex-col min-h-[350px]">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-4">
              {chart.title}
            </h3>
            <div className="flex-1 w-full relative">
              <ChartRenderer chart={chart} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChartRenderer({ chart }) {
  const commonAxisProps = {
    axisLine: { lineStyle: { color: '#3f3f46' } },
    splitLine: { lineStyle: { color: '#27272a', type: 'dashed' } },
    axisLabel: { color: '#a1a1aa' }
  };

  if (chart.type === 'risk_distribution' || chart.type === 'class_distribution') {
    const option = {
      tooltip: { 
        trigger: 'item',
        backgroundColor: '#18181b',
        borderColor: '#3f3f46',
        textStyle: { color: '#f4f4f5' }
      },
      legend: { 
        bottom: 0, 
        textStyle: { color: '#a1a1aa' },
        icon: 'circle'
      },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 5,
            borderColor: '#09090b',
            borderWidth: 2
          },
          label: { show: false },
          data: chart.data.map(d => ({
            name: d.name,
            value: d.value,
            itemStyle: { color: d.color }
          }))
        }
      ]
    };
    return <ReactECharts option={option} style={{ height: '100%', width: '100%', position: 'absolute' }} opts={{ renderer: 'svg' }} />;
  }

  if (chart.type === 'probability_ranking') {
    // Reverse data so the highest is at the top of the horizontal bar chart
    const data = [...chart.data].reverse();
    
    const option = {
      tooltip: { 
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: '#18181b',
        borderColor: '#3f3f46',
        textStyle: { color: '#f4f4f5' },
        formatter: (params) => {
          const p = params[0];
          return `ID: ${p.name}<br/>Probability: ${p.value}%`;
        }
      },
      grid: { left: '3%', right: '4%', bottom: '3%', top: '5%', containLabel: true },
      xAxis: { 
        type: 'value', 
        max: 100,
        ...commonAxisProps,
        axisLabel: { ...commonAxisProps.axisLabel, formatter: '{value}%' }
      },
      yAxis: { 
        type: 'category', 
        data: data.map(d => d.customer_id),
        ...commonAxisProps,
        splitLine: { show: false }
      },
      series: [
        {
          name: 'Probability',
          type: 'bar',
          data: data.map(d => ({
            value: d.probability,
            itemStyle: { color: d.color, borderRadius: [0, 4, 4, 0] }
          }))
        }
      ]
    };
    return <ReactECharts option={option} style={{ height: '100%', width: '100%', position: 'absolute' }} opts={{ renderer: 'svg' }} />;
  }

  if (chart.type === 'model_performance') {
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center space-y-6">
        <div>
          <p className="text-zinc-500 text-sm mb-1 uppercase tracking-wider">Test Accuracy</p>
          <p className="text-5xl font-mono text-zinc-100">
            {(chart.accuracy * 100).toFixed(1)}%
          </p>
        </div>
        <div className="grid grid-cols-2 gap-8 w-full max-w-[80%] pt-6 border-t border-zinc-800/50">
          <div>
            <p className="text-zinc-500 text-xs mb-1 uppercase tracking-wider">Target</p>
            <p className="text-zinc-300 font-mono text-sm truncate">{chart.target_column}</p>
          </div>
          <div>
            <p className="text-zinc-500 text-xs mb-1 uppercase tracking-wider">Predictions</p>
            <p className="text-zinc-300 font-mono text-sm">{chart.total_predicted.toLocaleString()}</p>
          </div>
        </div>
      </div>
    );
  }

  if (chart.type === 'feature_importance') {
    const data = [...chart.data].reverse();
    const option = {
      tooltip: { 
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: '#18181b',
        borderColor: '#3f3f46',
        textStyle: { color: '#f4f4f5' }
      },
      grid: { left: '3%', right: '4%', bottom: '3%', top: '5%', containLabel: true },
      xAxis: { 
        type: 'value',
        ...commonAxisProps,
        axisLabel: { ...commonAxisProps.axisLabel, formatter: '{value}%' }
      },
      yAxis: { 
        type: 'category', 
        data: data.map(d => d.feature),
        ...commonAxisProps,
        splitLine: { show: false }
      },
      series: [
        {
          name: 'Importance',
          type: 'bar',
          itemStyle: { color: '#6366f1', borderRadius: [0, 4, 4, 0] },
          data: data.map(d => d.importance)
        }
      ]
    };
    return <ReactECharts option={option} style={{ height: '100%', width: '100%', position: 'absolute' }} opts={{ renderer: 'svg' }} />;
  }

  if (chart.type === 'time_series_forecast') {
    const histData = chart.data.historical || [];
    const fcData = chart.data.forecast || [];
    
    // Create continuous x-axis labels
    const xLabels = [
      ...histData.map(d => d.date),
      ...fcData.map(d => d.date)
    ];

    const option = {
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#18181b',
        borderColor: '#3f3f46',
        textStyle: { color: '#f4f4f5' },
        axisPointer: { type: 'cross' }
      },
      legend: {
        bottom: 0,
        textStyle: { color: '#a1a1aa' },
        icon: 'circle'
      },
      grid: { left: '4%', right: '4%', bottom: '10%', top: '10%', containLabel: true },
      xAxis: {
        type: 'category',
        data: xLabels,
        ...commonAxisProps,
        boundaryGap: false,
      },
      yAxis: {
        type: 'value',
        ...commonAxisProps
      },
      series: [
        {
          name: 'Historical',
          type: 'line',
          data: [
            ...histData.map(d => d.value),
            ...fcData.map(() => '-') // nulls for forecast period
          ],
          itemStyle: { color: '#22c55e' },
          lineStyle: { width: 3 },
          showSymbol: false,
        },
        {
          name: 'Forecast',
          type: 'line',
          data: [
            ...histData.map(() => '-'),
            ...fcData.map(d => d.value)
          ],
          itemStyle: { color: '#6366f1' },
          lineStyle: { width: 3, type: 'dashed' },
          showSymbol: false,
        },
        {
          name: 'Confidence Interval (Lower)',
          type: 'line',
          data: [
            ...histData.map(() => '-'),
            ...fcData.map(d => d.lower)
          ],
          lineStyle: { opacity: 0 },
          stack: 'confidence-band',
          symbol: 'none',
          tooltip: { show: false }
        },
        {
          name: 'Confidence Interval (Upper)',
          type: 'line',
          data: [
            ...histData.map(() => '-'),
            ...fcData.map(d => d.upper - d.lower)
          ],
          lineStyle: { opacity: 0 },
          areaStyle: { color: '#6366f1', opacity: 0.1 },
          stack: 'confidence-band',
          symbol: 'none',
          tooltip: { show: false }
        }
      ]
    };
    return <ReactECharts option={option} style={{ height: '100%', width: '100%', position: 'absolute' }} opts={{ renderer: 'svg' }} />;
  }

  return <div className="text-zinc-500 flex items-center justify-center h-full text-sm">Unsupported chart type</div>;
}

function RiskIcon({ level }) {
  const color = riskColor(level);
  if (level === 'High') return <TbShieldOff className="w-14 h-14" style={{ color }} />;
  if (level === 'Medium') return <TbAlertTriangle className="w-14 h-14" style={{ color }} />;
  return <TbShieldCheck className="w-14 h-14" style={{ color }} />;
}

function riskColor(level) {
  if (level === 'High') return '#ef4444';
  if (level === 'Medium') return '#f59e0b';
  return '#22c55e';
}

function formatValue(v) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(v);
}
