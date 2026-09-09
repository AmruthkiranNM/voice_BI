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

  const targetColumn = prediction?.target_column || 'Value';

  // Single mode (gauge & profile view)
  if (mode === 'single') {
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
          <div key={idx} className={`panel-card flex flex-col ${(chart.type === 'time_series_forecast' || chart.type === 'grouped_time_series_forecast') ? 'col-span-1 md:col-span-2 min-h-[550px]' : 'min-h-[350px]'}`}>
            {(chart.type !== 'time_series_forecast' && chart.type !== 'grouped_time_series_forecast') && (
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-4">
                {chart.title}
              </h3>
            )}
            <div className="flex-1 w-full relative">
              <ChartRenderer chart={chart} targetColumn={targetColumn} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChartRenderer({ chart, targetColumn = 'Value' }) {
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
          let valLabel = isProb ? `${p.value}%` : (isCurrency ? '$' : '') + p.value.toLocaleString();
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
        axisLabel: { ...commonAxisProps.axisLabel, width: 100, overflow: 'truncate' }
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
    const displayFc = [];
    
    if (lastHist) {
      displayFc.push({
        date: lastHist.date,
        value: lastHist.value,
        lower: lastHist.value,
        upper: lastHist.value,
      });
    }
    displayFc.push(...fcData);

    const allDates = Array.from(new Set([
      ...displayHist.map(d => d.date),
      ...displayFc.map(d => d.date)
    ])).sort();
    
    const histMap = new Map(displayHist.map(d => [d.date, d.value]));
    const fcMap = new Map(displayFc.map(d => [d.date, d]));
    
    const histSeriesData = allDates.map(d => histMap.has(d) ? histMap.get(d) : '-');
    const fcSeriesData = allDates.map(d => fcMap.has(d) ? fcMap.get(d).value : '-');
    const lowerSeriesData = allDates.map(d => fcMap.has(d) ? fcMap.get(d).lower : '-');
    const upperSeriesData = allDates.map(d => {
      if (fcMap.has(d)) {
         const f = fcMap.get(d);
         if (f.upper != null && f.lower != null) return f.upper - f.lower;
      }
      return '-';
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
      return val.toLocaleString(undefined, {maximumFractionDigits:0});
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
          let html = `<div class="text-xs mb-2 text-zinc-400">Month:<br/><span class="text-zinc-100 font-medium">${formatTooltipDate(date)}</span></div>`;
          
          params.forEach(p => {
             if (p.seriesName === 'Actual' && p.value !== '-') {
                html += `<div class="flex items-center gap-4 mb-1"><div class="flex items-center gap-2"><span class="w-2 h-2 rounded-full" style="background:${p.color}"></span><span class="text-zinc-300">Actual ${metricLabel.toLowerCase()}:</span></div><span class="font-mono text-zinc-100 font-bold ml-auto">${isCurrency?'$':''}${Number(p.value).toLocaleString(undefined, {maximumFractionDigits: 2})}</span></div>`;
             }
             if (p.seriesName === 'Forecast' && p.value !== '-') {
                html += `<div class="flex items-center gap-4 mb-1"><div class="flex items-center gap-2"><span class="w-2 h-2 rounded-full" style="background:${p.color}"></span><span class="text-zinc-300">Forecast:</span></div><span class="font-mono text-zinc-100 font-bold ml-auto">${isCurrency?'$':''}${Number(p.value).toLocaleString(undefined, {maximumFractionDigits: 2})}</span></div>`;
             }
          });
          
          if (fcMap.has(date) && fcMap.get(date).lower != null && fcMap.get(date).upper != null) {
             const lower = fcMap.get(date).lower;
             const upper = fcMap.get(date).upper;
             if (lower !== upper) {
               html += `<div class="flex items-center gap-4 mt-2 pt-2 border-t border-zinc-700/50"><div class="flex items-center gap-2"><span class="w-2 h-2 rounded-sm bg-indigo-500/30 border border-indigo-500/50"></span><span class="text-zinc-400">Confidence interval:</span></div><span class="font-mono text-zinc-300 text-xs ml-auto">${isCurrency?'$':''}${Number(lower).toLocaleString(undefined, {maximumFractionDigits:0})} – ${isCurrency?'$':''}${Number(upper).toLocaleString(undefined, {maximumFractionDigits:0})}</span></div>`;
             }
          }
          
          return html;
        }
      },
      legend: {
        top: 0,
        textStyle: { color: '#a1a1aa' },
        icon: 'circle',
        data: [
           {name: 'Actual', icon: 'circle'},
           {name: 'Forecast', icon: 'path://M0,5 L10,5'},
           {name: 'Confidence interval', icon: 'roundRect'}
        ]
      },
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
             label: { show: true, position: 'start', formatter: 'Forecast starts', color: '#a1a1aa', fontSize: 10, padding: [0, 0, 10, 0] },
             lineStyle: { color: '#52525b', type: 'dashed', width: 1 },
             data: [ { xAxis: lastHist.date } ]
          } : null
        },
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
                  <p className="text-[10px] md:text-xs text-zinc-500 uppercase tracking-wider mb-1">Expected {metricLabel}</p>
                  <p className="text-xl md:text-2xl font-mono text-indigo-400 font-bold">
                     {isCurrency ? '$' : ''}{totalFc.toLocaleString(undefined, {maximumFractionDigits:2})}
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
         <div className="flex-1 w-full min-h-[400px] relative">
            <ReactECharts option={option} style={{ height: '100%', width: '100%', position: 'absolute' }} opts={{ renderer: 'svg' }} />
         </div>
      </div>
    );
  }
  if (chart.type === 'grouped_time_series_forecast') {
    const seriesGroups = chart.data || [];
    
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
      return val.toLocaleString(undefined, {maximumFractionDigits:0});
    };

    // Build series
    const echartSeries = [];
    let anyLastHistDate = null;
    let fcCount = 0;

    seriesGroups.forEach((groupData, idx) => {
       const histMap = new Map((groupData.historical || []).map(d => [d.date, d.value]));
       const fcMap = new Map((groupData.forecast || []).map(d => [d.date, d.value]));
       
       const lastHist = (groupData.historical || [])[(groupData.historical || []).length - 1];
       if (lastHist) {
          fcMap.set(lastHist.date, lastHist.value); // Join lines conceptually
          if (!anyLastHistDate) anyLastHistDate = lastHist.date;
       }
       
       if (idx === 0) fcCount = (groupData.forecast || []).length;
       
       const histSeriesData = allDates.map(d => histMap.has(d) ? histMap.get(d) : '-');
       const fcSeriesData = allDates.map(d => fcMap.has(d) ? fcMap.get(d) : '-');
       
       const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16', '#14b8a6', '#6366f1'];
       const color = colors[idx % colors.length];

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
          isHist: false
       });
    });

    if (anyLastHistDate && echartSeries.length > 0) {
       echartSeries[0].markLine = {
          symbol: ['none', 'none'],
          label: { show: true, position: 'start', formatter: 'Forecast starts', color: '#a1a1aa', fontSize: 10, padding: [0, 0, 10, 0] },
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
        formatter: function(params) {
          const date = params[0].name;
          let html = `<div class="text-xs mb-2 text-zinc-400">Month:<br/><span class="text-zinc-100 font-medium">${formatTooltipDate(date)}</span></div>`;
          
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
             else paramGroups[groupName].fc = p.value;
          });
          
          Object.keys(paramGroups).forEach(groupName => {
             const { color, hist, fc } = paramGroups[groupName];
             const displayVal = fc !== null ? fc : hist;
             const typeLabel = fc !== null ? 'Forecast' : 'Actual';
             
             html += `<div class="flex items-center gap-4 mb-1"><div class="flex items-center gap-2"><span class="w-2 h-2 rounded-full" style="background:${color}"></span><span class="text-zinc-300 font-medium">${groupName} <span class="text-zinc-500 font-normal ml-1">(${typeLabel})</span>:</span></div><span class="font-mono text-zinc-100 font-bold ml-auto">${isCurrency?'$':''}${Number(displayVal).toLocaleString(undefined, {maximumFractionDigits: 2})}</span></div>`;
          });
          return html;
        }
      },
      legend: {
        type: 'scroll',
        top: 0,
        textStyle: { color: '#a1a1aa' },
        icon: 'circle',
        data: seriesGroups.map(g => g.group)
      },
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
      series: echartSeries
    };
    
    return (
      <div className="flex flex-col h-full w-full">
         <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-8 mt-2 px-2">
            <div>
               <h2 className="text-lg md:text-xl font-bold text-zinc-100 uppercase tracking-wide">{humanTitle}</h2>
               <p className="text-zinc-400 text-sm mt-1">Expected {metricLabel.toLowerCase()} by group for the next {fcCount} periods</p>
            </div>
         </div>
         <div className="flex-1 w-full min-h-[400px] relative">
            <ReactECharts option={option} style={{ height: '100%', width: '100%', position: 'absolute' }} opts={{ renderer: 'svg' }} />
         </div>
      </div>
    );
  }


  return <div className="text-zinc-500 flex items-center justify-center h-full text-sm">Forecast visualization unavailable</div>;
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
