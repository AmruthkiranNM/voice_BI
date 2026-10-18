import { useEffect, useRef, useState } from 'react';
import {
  TbAlertTriangle, TbShieldCheck, TbShieldOff, TbChartBar,
  TbArrowsMaximize, TbArrowsMinimize, TbDownload, TbRefresh,
} from 'react-icons/tb';
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
  const charts = visualization?.charts || [];

  // Per-row predictions live under `row_predictions`; `predictions` is the
  // Per-row predictions live under `row_predictions`; `predictions` is the
  // legacy name kept for older payloads.
  const rowPredictions = prediction?.row_predictions || prediction?.predictions || [];
  const firstPred = rowPredictions[0] || null;

  const isForecasting = prediction?.task_type && prediction.task_type.includes('forecast');
  const meta = prediction?.model_metadata;
  const diag = prediction?.series_diagnostics;
  const hasMetadata = isForecasting && (meta || diag || prediction?.horizon);

  const accuracy = prediction?.model_accuracy;

  // Gate on whether there is anything to draw, not on one field's name. A
  // grouped forecast has neither `row_predictions` nor a top-level `forecast`
  // — its series live per group in `raw_forecast_results` and reach this
  // component as `visualization.charts`, so keying the guard off row
  // predictions hid every grouped and multidimensional forecast entirely.
  if (!charts.length && !firstPred && !isForecasting) {
    return (
      <div className="panel-card text-center py-10 text-zinc-400">
        <TbAlertTriangle className="w-8 h-8 mx-auto mb-3 text-amber-400" />
        <p className="text-sm">{result?.error || 'No prediction result available.'}</p>
      </div>
    );
  }

  const targetColumn = prediction?.target_column || 'Value';

  // Single mode (gauge & profile view)
  if (mode === 'single' && firstPred) {
    const probability = firstPred.probability;
    const riskLevel = firstPred.risk ?? 'Unknown';
    const featureImpacts = firstPred.feature_impacts || [];
    const rowData = firstPred.row_data || {};
    const isClassification = probability != null;

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
                {typeof firstPred.prediction === 'number' ? firstPred.prediction.toLocaleString('en-US', { maximumFractionDigits: 2 }) : firstPred.prediction}
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

  // Batch / forecast mode (multi-chart dashboard)
  return (
    <div className="bi-dashboard animate-in space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {charts.map((chart, idx) => {
          const isTimeSeries = chart.type === 'time_series_forecast'
            || chart.type === 'grouped_time_series_forecast';
          // Multi-dimensional group labels ("Canada - Organic Choco Syrup")
          // need the full row; in a half-width card they truncate to "Canada -
          // After…", which makes the ranking unreadable.
          const isWideRanking = chart.type === 'value_ranking'
            && ((chart.dimensions?.length || 0) > 1 || (chart.data?.length || 0) > 10);
          const fullWidth = isTimeSeries || isWideRanking;
          return (
          <div key={idx} className={`panel-card flex flex-col ${fullWidth ? 'col-span-1 md:col-span-2' : ''} ${isTimeSeries ? 'min-h-[550px]' : isWideRanking ? 'min-h-[520px]' : 'min-h-[350px]'}`}>
            {(chart.type !== 'time_series_forecast' && chart.type !== 'grouped_time_series_forecast') && (
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-4">
                {chart.title}
              </h3>
            )}
            <div className="flex-1 w-full relative">
              <ChartRenderer chart={chart} targetColumn={targetColumn} />
            </div>
            {chart.note && (
              <p className="mt-3 text-[11px] text-zinc-500 leading-relaxed">{chart.note}</p>
            )}
          </div>
          );
        })}
      </div>

      {hasMetadata && (
        <div className="panel-card mt-6">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-4 flex items-center gap-2">
            Technical Details
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
            {meta?.selected_model_label && (
              <div>
                <span className="block text-[10px] uppercase text-zinc-500 mb-1">Selected Model</span>
                <span className="text-zinc-200 font-mono">{meta.selected_model_label}</span>
              </div>
            )}
            {diag?.inferred_frequency && (
              <div>
                <span className="block text-[10px] uppercase text-zinc-500 mb-1">Frequency</span>
                <span className="text-zinc-200 capitalize font-mono">{diag.inferred_frequency}</span>
              </div>
            )}
            {prediction?.horizon != null && (
              <div>
                <span className="block text-[10px] uppercase text-zinc-500 mb-1">Horizon</span>
                <span className="text-zinc-200 font-mono">{prediction.horizon} periods</span>
              </div>
            )}
            {diag?.n_observed != null && (
              <div>
                <span className="block text-[10px] uppercase text-zinc-500 mb-1">Training Obs.</span>
                <span className="text-zinc-200 font-mono">{diag.n_observed}</span>
              </div>
            )}
            {meta?.selected_score != null && (
              <div>
                <span className="block text-[10px] uppercase text-zinc-500 mb-1">MASE</span>
                <span className={`font-mono ${meta.selected_score < 1.0 ? 'text-emerald-400' : meta.selected_score < 1.5 ? 'text-amber-400' : 'text-red-400'}`}>
                  {meta.selected_score.toFixed(4)}
                  {meta.selected_score < 1.0 ? ' \u2713' : ' (>1)'}
                </span>
              </div>
            )}
            {meta?.beats_naive != null && (() => {
              // Same rule as the backend's reliability_status, so the tile can
              // never contradict the written answer.
              const s = meta.selected_score;
              const state = !meta.beats_naive ? 'baseline'
                : (s != null && s < 1 ? 'validated' : 'weak');
              return (
                <div>
                  <span className="block text-[10px] uppercase text-zinc-500 mb-1">Reliability</span>
                  <span className="font-mono" style={{ color: RELIABILITY_COLOR[state] }}>
                    {RELIABILITY_LABEL[state]}
                  </span>
                </div>
              );
            })()}
            {meta?.selection_method && (
              <div>
                <span className="block text-[10px] uppercase text-zinc-500 mb-1">Selection Method</span>
                <span className="text-zinc-400 font-mono text-[10px]">{meta.selection_method.replace(/_/g, ' ')}</span>
              </div>
            )}
          </div>
          {meta?.notes && meta.notes.length > 0 && (
            <div className="border-t border-zinc-700 pt-3 mt-2 space-y-1">
              {meta.notes.map((note, i) => (
                <p key={i} className="text-[11px] text-amber-300/80 leading-relaxed flex gap-2">
                  <span className="mt-0.5 shrink-0">&#9888;</span>
                  <span>{note}</span>
                </p>
              ))}
            </div>
          )}
          {diag?.warnings && diag.warnings.length > 0 && (
            <div className="border-t border-zinc-700 pt-3 mt-2 space-y-1">
              {diag.warnings.map((w, i) => (
                <p key={i} className="text-[11px] text-zinc-500 leading-relaxed flex gap-2">
                  <span className="mt-0.5 shrink-0">&#8505;</span>
                  <span>{w}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Shared by every chart in this file, including GroupedForecastChart, so it
// lives at module scope rather than inside one component.
const commonAxisProps = {
  axisLine: { lineStyle: { color: '#3f3f46' } },
  splitLine: { lineStyle: { color: '#27272a', type: 'dashed' } },
  axisLabel: { color: '#a1a1aa' }
};

function ChartRenderer({ chart, targetColumn = 'Value' }) {
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

  if (chart.type === 'probability_ranking' || chart.type === 'value_ranking') {
    const data = [...chart.data].reverse();
    const isProb = chart.type === 'probability_ranking';
    const isCurrency = !isProb && ['amount', 'revenue', 'price', 'salary', 'sales'].some(w => targetColumn.toLowerCase().includes(w));
    
    const option = {
      tooltip: { 
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: '#18181b',
        borderColor: '#3f3f46',
        textStyle: { color: '#f4f4f5' },
        formatter: (params) => {
          const p = params[0];
          let valLabel = isProb ? `${p.value}%` : (isCurrency ? '$' : '') + p.value.toLocaleString('en-US');
          return `${chart.dimension === 'group' ? 'Group' : 'ID'}: ${p.name}<br/>${isProb ? 'Probability' : 'Value'}: ${valLabel}`;
        }
      },
      grid: { left: '3%', right: '4%', bottom: '3%', top: '5%', containLabel: true },
      xAxis: { 
        type: 'value', 
        max: isProb ? 100 : undefined,
        ...commonAxisProps,
        axisLabel: { ...commonAxisProps.axisLabel, formatter: isProb ? '{value}%' : (value => (isCurrency ? '$' : '') + (value >= 1e6 ? (value/1e6).toFixed(1) + 'M' : value >= 1e3 ? (value/1e3).toFixed(1) + 'K' : value)) }
      },
      yAxis: { 
        type: 'category', 
        data: data.map(d => chart.dimension === 'group' ? d.group : d.customer_id),
        ...commonAxisProps,
        splitLine: { show: false },
        axisLabel: {
          ...commonAxisProps.axisLabel,
          // One dimension is a short word; several are "Canada - Organic Choco
          // Syrup". Size the gutter to the labels actually present.
          width: (chart.dimensions?.length || 1) > 1 ? 210 : 120,
          overflow: 'truncate',
        }
      },
      series: [
        {
          name: isProb ? 'Probability' : 'Value',
          type: 'bar',
          data: data.map(d => ({
            value: isProb ? d.probability : d.value,
            itemStyle: { color: d.color || '#6366f1', borderRadius: [0, 4, 4, 0] }
          }))
        }
      ]
    };
    return <ReactECharts option={option} style={{ height: '100%', width: '100%', position: 'absolute' }} opts={{ renderer: 'svg' }} />;
  }

  if (chart.type === 'value_distribution') {
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
        type: 'category', 
        data: chart.data.map(d => d.range),
        ...commonAxisProps,
        axisLabel: { ...commonAxisProps.axisLabel, interval: 0, rotate: 30 }
      },
      yAxis: { 
        type: 'value',
        ...commonAxisProps
      },
      series: [
        {
          name: 'Count',
          type: 'bar',
          data: chart.data.map(d => d.count),
          itemStyle: { color: '#8b5cf6', borderRadius: [4, 4, 0, 0] }
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
            <p className="text-zinc-300 font-mono text-sm">{chart.total_predicted.toLocaleString('en-US')}</p>
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
    
    const isCurrency = ['amount', 'revenue', 'price', 'salary', 'sales'].some(w => targetColumn.toLowerCase().includes(w));
    
    let metricLabel = targetColumn.replace(/_/g, ' ');
    if (metricLabel.toUpperCase() === 'AMOUNT') metricLabel = 'Sales revenue';
    else metricLabel = metricLabel.charAt(0).toUpperCase() + metricLabel.slice(1);

    let humanTitle = chart.title;
    if (chart.title.toLowerCase().startsWith('forecast:')) {
      humanTitle = `${metricLabel} Forecast`;
    }

    const lastHist = histData[histData.length - 1];
    const displayHist = [...histData];
    const displayFc = [...fcData];


    const allDates = Array.from(new Set([
      ...displayHist.map(d => d.date),
      ...displayFc.map(d => d.date)
    ])).sort();
    
    const histMap = new Map(displayHist.map(d => [d.date, d.value]));
    const fcMap = new Map(displayFc.map(d => [d.date, d]));
    
    const histSeriesData = allDates.map(d => histMap.has(d) ? histMap.get(d) : '-');
    // The dashed forecast starts from the last actual point so the two lines
    // join instead of leaving a gap. That point is the real last value, not a
    // forecast, and the tooltip does not label it as one.
    const bridgeDate = lastHist && lastHist.value != null && !fcMap.has(lastHist.date) ? lastHist.date : null;
    const fcSeriesData = allDates.map(d => fcMap.has(d) ? fcMap.get(d).value
      : (d === bridgeDate ? lastHist.value : '-'));
    // The method re-fitted without the last few known months and asked to
    // predict them: drawn over the history so the level forecast can be seen
    // against real swings it did not get to learn from.
    const holdoutMap = new Map((chart.holdout || []).map(h => [h.date || h.period, h.predicted]));
    const holdoutSeriesData = allDates.map(d => holdoutMap.has(d) ? holdoutMap.get(d) : '-');
    const hasHoldout = holdoutMap.size > 0;
    const hasBand = fcData.some(f => f.lower != null && f.upper != null);
    const lowerSeriesData = allDates.map(d => fcMap.has(d) ? fcMap.get(d).lower
      : (d === bridgeDate && hasBand ? lastHist.value : '-'));
    const upperSeriesData = allDates.map(d => {
      if (fcMap.has(d)) {
         const f = fcMap.get(d);
         if (f.upper != null && f.lower != null) return f.upper - f.lower;
      }
      return d === bridgeDate && hasBand ? 0 : '-';
    });

    const totalFc = fcData.reduce((sum, d) => sum + (d.value || 0), 0);
    const endDateStr = fcData.length > 0 ? fcData[fcData.length - 1].date : '';
    
    const formatDateObj = (dateStr) => {
      try {
         const d = new Date(dateStr);
         return isNaN(d.getTime()) ? null : d;
      } catch(e) { return null; }
    };

    const formatTooltipDate = (dateStr) => {
       const d = formatDateObj(dateStr);
       return d ? d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }) : dateStr;
    };

    const formatCurrencyNum = (val) => {
      if (val === 0) return '0';
      const abs = Math.abs(val);
      if (abs >= 1e6) return (val / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
      if (abs >= 1e3) return (val / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
      return val.toLocaleString('en-US', {maximumFractionDigits:0});
    };

    const option = {
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#18181b',
        borderColor: '#3f3f46',
        textStyle: { color: '#f4f4f5' },
        axisPointer: { type: 'line', lineStyle: { color: '#52525b', type: 'dashed' } },
        formatter: function(params) {
          const date = params[0].name;
          let html = `<div style="font-size:12px;margin-bottom:8px;color:#a1a1aa">Period:<br/><span style="color:#f4f4f5;font-weight:500">${formatTooltipDate(date)}</span></div>`;
          
          params.forEach(p => {
             if (p.seriesName === 'Actual' && p.value !== '-') {
                html += `<div class="flex items-center gap-4 mb-1"><div class="flex items-center gap-2"><span class="w-2 h-2 rounded-full" style="background:${p.color}"></span><span style="color:#d4d4d8">Actual ${metricLabel.toLowerCase()}:</span></div><span style="font-family:ui-monospace,monospace;color:#fafafa;font-weight:700;margin-left:auto">${isCurrency?'$':''}${Number(p.value).toLocaleString('en-US', {maximumFractionDigits: 2})}</span></div>`;
             }
             if (p.seriesName === 'Forecast' && p.value !== '-' && fcMap.has(date)) {
                html += `<div class="flex items-center gap-4 mb-1"><div class="flex items-center gap-2"><span class="w-2 h-2 rounded-full" style="background:${p.color}"></span><span style="color:#d4d4d8">Forecast:</span></div><span style="font-family:ui-monospace,monospace;color:#fafafa;font-weight:700;margin-left:auto">${isCurrency?'$':''}${Number(p.value).toLocaleString('en-US', {maximumFractionDigits: 2})}</span></div>`;
             }
          });
          
          if (holdoutMap.has(date)) {
             html += `<div style="display:flex;align-items:center;gap:16px;margin-top:4px"><span style="color:#a1a1aa">Test prediction (made without this month):</span><span style="font-family:ui-monospace,monospace;color:#d4d4d8;margin-left:auto">${isCurrency?'$':''}${Number(holdoutMap.get(date)).toLocaleString('en-US', {maximumFractionDigits:0})}</span></div>`;
          }
          if (fcMap.has(date) && fcMap.get(date).lower != null && fcMap.get(date).upper != null) {
             const lower = fcMap.get(date).lower;
             const upper = fcMap.get(date).upper;
             if (lower !== upper) {
               html += `<div style="display:flex;align-items:center;gap:16px;margin-top:8px;padding-top:8px;border-top:1px solid rgba(63,63,70,.6)"><div class="flex items-center gap-2"><span class="w-2 h-2 rounded-sm bg-indigo-500/30 border border-indigo-500/50"></span><span style="color:#a1a1aa">95% likely range:</span></div><span style="font-family:ui-monospace,monospace;color:#d4d4d8;font-size:12px;margin-left:auto">${isCurrency?'$':''}${Number(lower).toLocaleString('en-US', {maximumFractionDigits:0})} – ${isCurrency?'$':''}${Number(upper).toLocaleString('en-US', {maximumFractionDigits:0})}</span></div>`;
             }
          }
          
          return html;
        }
      },
      // Drawn as HTML above the chart instead: the ECharts legend stacked
      // its three entries on top of each other under the app's CSS.
      legend: { show: false },
      grid: { left: '2%', right: '2%', bottom: '5%', top: '15%', containLabel: true },
      xAxis: {
        type: 'category',
        data: allDates,
        ...commonAxisProps,
        boundaryGap: false,
        axisLabel: {
           color: '#a1a1aa',
           hideOverlap: true,
           formatter: function(value, index) {
              const d = formatDateObj(value);
              if (!d) return value;
              const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
              if (d.getMonth() === 0 || index === 0 || index === allDates.length - 1) return `${months[d.getMonth()]} ${d.getFullYear()}`;
              return months[d.getMonth()];
           }
        }
      },
      yAxis: {
        type: 'value',
        name: metricLabel,
        nameTextStyle: { color: '#71717a', padding: [0, 0, 10, 0] },
        ...commonAxisProps,
        splitLine: { lineStyle: { color: '#27272a', type: 'solid', opacity: 0.5 } },
        axisLabel: {
           color: '#a1a1aa',
           formatter: function(value) {
              return (isCurrency ? '$' : '') + formatCurrencyNum(value);
           }
        }
      },
      series: [
        {
          name: 'Actual',
          type: 'line',
          data: histSeriesData,
          itemStyle: { color: '#22c55e' },
          lineStyle: { width: 2 },
          showSymbol: false,
          z: 3
        },
        {
          name: 'Forecast',
          type: 'line',
          data: fcSeriesData,
          itemStyle: { color: '#6366f1' },
          lineStyle: { width: 2, type: 'dashed' },
          showSymbol: true,
          symbol: 'circle',
          symbolSize: 6,
          z: 2,
          markLine: lastHist ? {
             symbol: ['none', 'none'],
             label: { show: true, position: 'end', formatter: 'Forecast starts', color: '#a1a1aa', fontSize: 10 },
             lineStyle: { color: '#52525b', type: 'dashed', width: 1 },
             data: [ { xAxis: lastHist.date } ]
          } : null
        },
        ...(hasHoldout ? [{
          name: 'Test prediction',
          type: 'line',
          data: holdoutSeriesData,
          itemStyle: { color: '#a1a1aa' },
          lineStyle: { width: 2, type: 'dotted' },
          showSymbol: true,
          symbol: 'emptyCircle',
          symbolSize: 5,
          z: 4,
          tooltip: { show: false },
        }] : []),
        {
          name: 'CI Lower Base',
          type: 'line',
          data: lowerSeriesData,
          lineStyle: { opacity: 0 },
          stack: 'confidence-band',
          symbol: 'none',
          tooltip: { show: false }
        },
        {
          name: 'Confidence interval',
          type: 'line',
          data: upperSeriesData,
          lineStyle: { opacity: 0 },
          areaStyle: { color: '#6366f1', opacity: 0.15 },
          stack: 'confidence-band',
          symbol: 'none',
          tooltip: { show: false }
        }
      ]
    };
    
    return (
      <div className="flex flex-col h-full w-full">
         <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-8 mt-2 px-2">
            <div>
               <h2 className="text-lg md:text-xl font-bold text-zinc-100 uppercase tracking-wide">{humanTitle}</h2>
               <p className="text-zinc-400 text-sm mt-1">Historical performance and expected {metricLabel.toLowerCase()} for the next {fcData.length} periods</p>
            </div>
            <div className="flex space-x-6 md:space-x-8 text-right mt-4 md:mt-0">
               <div>
                  <p className="text-[10px] md:text-xs text-zinc-500 uppercase tracking-wider mb-1">Total forecast, {fcData.length} periods</p>
                  <p className="text-xl md:text-2xl font-mono text-indigo-400 font-bold">
                     {isCurrency ? '$' : ''}{totalFc.toLocaleString('en-US', {maximumFractionDigits:2})}
                  </p>
               </div>
               <div>
                  <p className="text-[10px] md:text-xs text-zinc-500 uppercase tracking-wider mb-1">Forecast End</p>
                  <p className="text-lg md:text-xl text-zinc-300">
                     {formatTooltipDate(endDateStr) || 'N/A'}
                  </p>
               </div>
            </div>
         </div>
         <div className="flex items-center gap-5 px-2 mb-2 text-xs text-zinc-400">
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: '#22c55e' }} />Actual</span>
            <span className="flex items-center gap-1.5"><span className="w-4 border-t-2 border-dashed" style={{ borderColor: '#6366f1' }} />Forecast</span>
            {fcData.some(d => d.lower != null && d.upper != null) && (
              <span className="flex items-center gap-1.5"><span className="w-3 h-2.5 rounded-sm" style={{ background: 'rgba(99,102,241,0.2)' }} />95% likely range</span>
            )}
            {hasHoldout && (
              <span className="flex items-center gap-1.5" title="The same method, re-fitted without these months, predicting them">
                <span className="w-4 border-t-2 border-dotted" style={{ borderColor: '#a1a1aa' }} />Tested on past periods
              </span>
            )}
            {chart.model && (
              <span className="ml-auto text-zinc-500">
                Model: <span className="text-zinc-300">{chart.model}</span>
                {chart.reliability && (
                  <> · <span style={{ color: RELIABILITY_COLOR[chart.reliability] }}>{RELIABILITY_LABEL[chart.reliability]}</span></>
                )}
              </span>
            )}
         </div>
         <div className="flex-1 w-full min-h-[400px] relative">
            <ReactECharts option={option} style={{ height: '100%', width: '100%', position: 'absolute' }} opts={{ renderer: 'svg' }} />
         </div>
         <ForecastExplanation sentences={chart.explanation} />
      </div>
    );
  }
  if (chart.type === 'grouped_time_series_forecast') {
    return <GroupedForecastChart chart={chart} targetColumn={targetColumn} />;
  }


  return <div className="text-zinc-500 flex items-center justify-center h-full text-sm">Forecast visualization unavailable</div>;
}

const RELIABILITY_COLOR = {
  validated: '#34d399',
  weak: '#f87171',
  baseline: '#fbbf24',
  not_validated: '#a1a1aa',
};

const RELIABILITY_LABEL = {
  validated: 'Validated',
  weak: 'Weak (indicative)',
  baseline: 'Baseline only',
  not_validated: 'Not validated',
};

/**
 * "Why does the forecast look like this?" — the engine's measured reasons
 * (trend vs swing, history needed for seasonality, models tested, what the
 * band means). Shown under every forecast line, single or focused.
 */
function ForecastExplanation({ sentences }) {
  const [open, setOpen] = useState(true);
  if (!sentences || !sentences.length) return null;
  return (
    <div className="mt-3 mx-2 rounded-lg border border-zinc-700/60 bg-zinc-900/40 px-4 py-3">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 hover:text-zinc-200"
      >
        {open ? '▾' : '▸'} Why does the forecast look like this?
      </button>
      {open && (
        <ul className="mt-2 space-y-1.5 list-disc pl-5">
          {sentences.map((s, i) => (
            <li key={i} className="text-xs text-zinc-400 leading-relaxed">{s}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Grouped forecast: every series at once, or one series in focus.
 *
 * With many series drawn together, each forecast is only its point estimate,
 * and a flat point estimate next to a jagged history looks like a claim of
 * certainty. Focusing a series re-draws it with the prediction interval the
 * backend computed from its validation residuals, which is where the history's
 * variability actually shows up in a forecast. Nothing is recomputed here:
 * the values plotted are the values the API returned.
 */
//: How many series the overview draws. More than this is unreadable as lines
//: and unexplainable in a tooltip; the full list is in the answer text.
//: Default: every series, matching the answer text. 0 means "all".
const GROUPED_TOP_N = 0;
//: 0 means "all series".
const GROUPED_TOP_N_OPTIONS = [3, 5, 10, 0];

//: Beyond the fixed palette, spread hues evenly so 20+ series stay distinct.
const seriesColor = (idx, total) =>
  idx < 10 ? SERIES_COLORS[idx] : `hsl(${Math.round((idx * 360) / Math.max(total, 1))}, 65%, 50%)`;
const SERIES_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
                       '#ec4899', '#06b6d4', '#84cc16', '#14b8a6', '#6366f1'];

function ToolbarBtn({ onClick, title, icon, active }) {
  return (
    <button type="button" title={title} onClick={onClick}
            className={`bi-control-btn ${active ? 'active' : ''}`}>
      {icon}
    </button>
  );
}

//: One plain sentence per validation outcome, for the focused view.
const RELIABILITY_PLAIN = {
  validated: 'Reliable — beat the simple "same as last month" baseline on past data.',
  weak: 'Low reliability — use as a rough guide only.',
  baseline: 'No model beat "same as last month", so that is the forecast.',
  not_validated: 'Not enough history to test this forecast.',
};

//: topN value for "only the series the question is about".
const RELEVANT = -1;

function GroupedForecastChart({ chart, targetColumn = 'Value' }) {
  // A "top 5" question draws the series it is about (current top 5 plus any
  // entering the forecast top 5), not every product; the rest stay one click away.
  const focusGroups = chart.focus_groups || [];
  const defaultTopN = focusGroups.length ? RELEVANT : GROUPED_TOP_N;
  const [focus, setFocus] = useState(null);
  const [topN, setTopN] = useState(defaultTopN);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  // Leaving fullscreen with Esc must also reset our state.
  useEffect(() => {
    const onChange = () => { if (!document.fullscreenElement) setIsFullscreen(false); };
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen?.();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen?.();
      setIsFullscreen(false);
    }
  };

  const exportPng = () => {
    const instance = chartRef.current?.getEchartsInstance();
    if (!instance) return;
    const a = document.createElement('a');
    a.href = instance.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#FFFFFF' });
    a.download = 'forecast.png';
    a.click();
  };

  const reset = () => { setFocus(null); setTopN(defaultTopN); };

  // Series arrive ranked by forecast total, so the first N are the largest.
  const groups = topN === RELEVANT
    ? (chart.data || []).filter(g => focusGroups.includes(g.group))
    : topN === 0 ? (chart.data || []) : (chart.data || []).slice(0, topN);
  const totalSeries = chart.total || (chart.data || []).length;
  // One series on screen: draw it with its band and explanation straight
  // away. The multi-series view has no band, so a lone flat line there reads
  // as a claim of certainty.
  const focused = focus ? groups.find(g => g.group === focus)
    : (groups.length === 1 ? groups[0] : null);

  const toolbar = (
    <div className="bi-controls-bar">
      <div className="bi-topn-wrap">
        <select value={topN} onChange={(e) => { setTopN(Number(e.target.value)); setFocus(null); }}
                className="bi-topn-select" title="How many series to show">
          {focusGroups.length > 0 && (
            <option value={RELEVANT}>{`Relevant (${focusGroups.length})`}</option>
          )}
          {GROUPED_TOP_N_OPTIONS.map(n => (
            <option key={n} value={n}>{n === 0 ? `All (${(chart.data || []).length})` : `Top ${n}`}</option>
          ))}
        </select>
      </div>
      <div className="bi-sep" />
      {!focused && (
        <ToolbarBtn onClick={exportPng} title="Download PNG" icon={<TbDownload size={13} />} />
      )}
      <ToolbarBtn onClick={toggleFullscreen} title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
                  icon={isFullscreen ? <TbArrowsMinimize size={13} /> : <TbArrowsMaximize size={13} />} />
      <ToolbarBtn onClick={reset} title="Reset" icon={<TbRefresh size={13} />} />
    </div>
  );

  // One wrapper for both views so fullscreen covers whichever is showing.
  const frame = (content) => (
    <div ref={containerRef}
         className={`flex flex-col h-full w-full ${isFullscreen ? 'bi-chart-fullscreen bg-white p-6 overflow-auto' : ''}`}>
      {content}
    </div>
  );

  const focusBar = (
    <div className="px-2 mb-4">
      <div className="flex justify-end mb-2">{toolbar}</div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setFocus(null)}
          className={`px-3 py-1 rounded-full text-xs border transition-colors ${!focused ? 'bg-zinc-100 text-zinc-900 border-zinc-100' : 'text-zinc-400 border-zinc-700 hover:border-zinc-500'}`}
        >
          All series
        </button>
        {groups.map((g, idx) => (
          <button
            key={g.group}
            type="button"
            onClick={() => setFocus(g.group)}
            className={`px-3 py-1 rounded-full text-xs border transition-colors flex items-center gap-1.5 ${focused && focused.group === g.group ? 'bg-zinc-100 text-zinc-900 border-zinc-100' : 'text-zinc-300 border-zinc-700 hover:border-zinc-500'}`}
          >
            <span className="w-2 h-2 rounded-full" style={{ background: seriesColor(idx, groups.length) }} />
            {g.group}
          </button>
        ))}
      </div>
      <p className="text-[11px] text-zinc-500 mt-2">
        {focused
          ? 'Shaded area: the 95% likely range for each future value, sized from the model’s errors on held-out months.'
          : topN === RELEVANT
            ? (chart.top_n && chart.focus_kind === 'comparison'
                ? `Current top ${chart.top_n} and any entering the forecast top ${chart.top_n} (${groups.length} of ${totalSeries}). Choose "All" to see every series; click one to see its forecast range.`
                : chart.top_n
                ? `Forecast top ${chart.top_n} of ${totalSeries}. Choose "All" to see every series; click one to see its forecast range.`
                : `${groups.length} of ${totalSeries} series. Click one to see its forecast range.`)
          : groups.length >= totalSeries
            ? `All ${totalSeries} series. Click one to see its forecast range.`
            : `Top ${groups.length} of ${totalSeries} by forecast total. Click one to see its forecast range.`}
      </p>
    </div>
  );

  if (focused) {
    const single = {
      type: 'time_series_forecast',
      title: `${chart.title}: ${focused.group}`,
      data: { historical: focused.historical || [], forecast: focused.forecast || [] },
      // Model and reliability are already stated in the line above the chart.
      explanation: focused.explanation || [],
      holdout: focused.holdout || [],
    };
    return frame(
      <>
        {focusBar}
        {focused.model && (
          <div className="px-2 mb-2 text-xs text-zinc-400">
            Model: <span className="text-zinc-200">{focused.model}</span>
            {' — '}
            <span style={{ color: RELIABILITY_COLOR[focused.reliability] || '#a1a1aa' }}>
              {RELIABILITY_PLAIN[focused.reliability] || ''}
            </span>
          </div>
        )}
        <div className={`flex-1 w-full relative ${isFullscreen ? 'min-h-[70vh]' : 'min-h-[400px]'}`}>
          <ChartRenderer chart={single} targetColumn={targetColumn} />
        </div>
      </>
    );
  }

    const seriesGroups = groups;

    // Data Consistency Check
    if (seriesGroups.length === 0 || seriesGroups.some(g => !g.forecast || g.forecast.length === 0)) {
        return <div className="text-zinc-500 flex items-center justify-center h-full text-sm">Forecast visualization is unavailable because the prediction result is incomplete.</div>;
    }

    const isCurrency = ['amount', 'revenue', 'price', 'salary', 'sales'].some(w => targetColumn.toLowerCase().includes(w));
    
    let metricLabel = targetColumn.replace(/_/g, ' ');
    if (metricLabel.toUpperCase() === 'AMOUNT') metricLabel = 'Sales revenue';
    else metricLabel = metricLabel.charAt(0).toUpperCase() + metricLabel.slice(1);

    let humanTitle = chart.title;

    // Collect all dates
    const allDatesSet = new Set();
    seriesGroups.forEach(g => {
       (g.historical || []).forEach(d => allDatesSet.add(d.date));
       (g.forecast || []).forEach(d => allDatesSet.add(d.date));
    });
    const allDates = Array.from(allDatesSet).sort();

    const formatDateObj = (dateStr) => {
      try {
         const d = new Date(dateStr);
         return isNaN(d.getTime()) ? null : d;
      } catch(e) { return null; }
    };

    const formatTooltipDate = (dateStr) => {
       const d = formatDateObj(dateStr);
       return d ? d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }) : dateStr;
    };

    const formatCurrencyNum = (val) => {
      if (val === 0) return '0';
      const abs = Math.abs(val);
      if (abs >= 1e6) return (val / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
      if (abs >= 1e3) return (val / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
      return val.toLocaleString('en-US', {maximumFractionDigits:0});
    };

    // Build series
    const echartSeries = [];
    let anyLastHistDate = null;
    let fcCount = 0;

    seriesGroups.forEach((groupData, idx) => {
       const histMap = new Map((groupData.historical || []).map(d => [d.date, d.value]));
       const fcMap = new Map((groupData.forecast || []).map(d => [d.date, d.value]));
       
       const lastHist = (groupData.historical || [])[(groupData.historical || []).length - 1];
       if (lastHist && !anyLastHistDate) {
          anyLastHistDate = lastHist.date;
       }
       
       if (idx === 0) fcCount = (groupData.forecast || []).length;
       
       const histSeriesData = allDates.map(d => histMap.has(d) ? histMap.get(d) : '-');
       // Each dashed forecast starts from its own last actual point, so it
       // joins its history line; that point is the real value, and the
       // tooltip reports it as actual, not forecast.
       const bridgeDate = lastHist && lastHist.value != null && !fcMap.has(lastHist.date) ? lastHist.date : null;
       const fcSeriesData = allDates.map(d => fcMap.has(d) ? fcMap.get(d)
         : (d === bridgeDate ? lastHist.value : '-'));

       // Same palette as the series buttons, so a button and its line match.
       const color = seriesColor(idx, seriesGroups.length);

       echartSeries.push({
          name: groupData.group + ' (Historical)',
          type: 'line',
          data: histSeriesData,
          itemStyle: { color: color },
          lineStyle: { width: 2, opacity: 0.5 },
          showSymbol: false,
          z: 3,
          groupName: groupData.group,
          isHist: true,
          tooltip: { show: false } // Handled manually
       });

       echartSeries.push({
          name: groupData.group,
          type: 'line',
          data: fcSeriesData,
          itemStyle: { color: color },
          lineStyle: { width: 2, type: 'dashed' },
          showSymbol: true,
          symbol: 'circle',
          symbolSize: 6,
          z: 4,
          groupName: groupData.group,
          isHist: false,
          bridgeDate,
       });
    });

    if (anyLastHistDate && echartSeries.length > 0) {
       echartSeries[0].markLine = {
          symbol: ['none', 'none'],
          label: { show: true, position: 'end', formatter: 'Forecast starts', color: '#a1a1aa', fontSize: 10 },
          lineStyle: { color: '#52525b', type: 'dashed', width: 1 },
          data: [ { xAxis: anyLastHistDate } ]
       };
    }

    const option = {
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#18181b',
        borderColor: '#3f3f46',
        textStyle: { color: '#f4f4f5' },
        axisPointer: { type: 'line', lineStyle: { color: '#52525b', type: 'dashed' } },
        confine: true,
        formatter: function(params) {
          const date = params[0].name;
          let html = `<div style="font-size:12px;margin-bottom:4px;color:#f4f4f5;font-weight:500">${formatTooltipDate(date)}</div>`;

          const validParams = params.filter(p => p.value !== '-');
          const paramGroups = {};
          
          validParams.forEach(p => {
             const seriesDef = echartSeries[p.seriesIndex];
             if (!seriesDef) return;
             const groupName = seriesDef.groupName;
             const isHist = seriesDef.isHist;
             if (!paramGroups[groupName]) {
                 paramGroups[groupName] = { color: p.color, hist: null, fc: null };
             }
             if (isHist) paramGroups[groupName].hist = p.value;
             else if (date !== seriesDef.bridgeDate) paramGroups[groupName].fc = p.value;
          });
          
          // With a dozen series a full list overflows the chart, so the tooltip
          // shows the largest few for this month and summarises the rest.
          // Model details live in the series chips and the focused view.
          const TOOLTIP_LIMIT = 5;
          const entries = Object.keys(paramGroups).map(groupName => {
             const { color, hist, fc } = paramGroups[groupName];
             return { groupName, color, isFc: fc !== null, value: Number(fc !== null ? fc : hist) };
          }).sort((a, b) => b.value - a.value);
          const isFcMonth = entries.some(e => e.isFc);
          html += `<div style="font-size:11px;color:#a1a1aa;margin-bottom:6px">${isFcMonth ? 'Forecast' : 'Actual'} · top ${Math.min(TOOLTIP_LIMIT, entries.length)} of ${entries.length}</div>`;

          entries.slice(0, TOOLTIP_LIMIT).forEach(({ groupName, color, value }) => {
             html +=`<div style="display:flex;gap:12px;align-items:center;font-size:12px;margin-bottom:3px"><span style="width:8px;height:8px;border-radius:50%;background:${color}"></span><span style="color:#d4d4d8;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${groupName}</span><span style="font-family:ui-monospace,monospace;color:#fafafa;font-weight:700;margin-left:auto">${isCurrency?'$':''}${Number(value).toLocaleString('en-US', {maximumFractionDigits: 0})}</span></div>`;
          });
          if (entries.length > TOOLTIP_LIMIT) {
             html += `<div style="font-size:11px;color:#71717a;margin-top:4px">+${entries.length - TOOLTIP_LIMIT} more</div>`;
          }
          return html;
        }
      },
      // The series buttons above already act as the legend.
      legend: { show: false },
      grid: { left: '2%', right: '2%', bottom: '5%', top: '8%', containLabel: true },
      xAxis: {
        type: 'category',
        data: allDates,
        ...commonAxisProps,
        boundaryGap: false,
        axisLabel: {
           color: '#a1a1aa',
           hideOverlap: true,
           formatter: function(value, index) {
              const d = formatDateObj(value);
              if (!d) return value;
              const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
              if (d.getMonth() === 0 || index === 0 || index === allDates.length - 1) return `${months[d.getMonth()]} ${d.getFullYear()}`;
              return months[d.getMonth()];
           }
        }
      },
      yAxis: {
        type: 'value',
        name: metricLabel,
        nameTextStyle: { color: '#71717a', padding: [0, 0, 10, 0] },
        ...commonAxisProps,
        splitLine: { lineStyle: { color: '#27272a', type: 'solid', opacity: 0.5 } },
        axisLabel: {
           color: '#a1a1aa',
           formatter: function(value) {
              return (isCurrency ? '$' : '') + formatCurrencyNum(value);
           }
        }
      },
      series: echartSeries
    };
    
    return frame(
      <>
         <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-4 mt-2 px-2">
            <div>
               <h2 className="text-lg md:text-xl font-bold text-zinc-100 uppercase tracking-wide">{humanTitle}</h2>
               <p className="text-zinc-400 text-sm mt-1">Expected {metricLabel.toLowerCase()} for the next {fcCount} months</p>
            </div>
         </div>
         {focusBar}
         <div className={`flex-1 w-full relative ${isFullscreen ? 'min-h-[70vh]' : 'min-h-[400px]'}`}>
            <ReactECharts ref={chartRef} option={option} notMerge
                          style={{ height: '100%', width: '100%', position: 'absolute' }} opts={{ renderer: 'svg' }} />
         </div>
      </>
    );
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
    if (Number.isInteger(v)) return v.toLocaleString('en-US');
    return v.toLocaleString('en-US', { maximumFractionDigits: 2 });
  }
  return String(v);
}
