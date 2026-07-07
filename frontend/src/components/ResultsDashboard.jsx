import InsightPanel from './InsightPanel';
import BIChartPanel from './BIChartPanel';
import ResultTable from './ResultTable';
import DatasetSummary from './DatasetSummary';
import KPICard, { detectKpiMetrics } from './KPICard';
import TechnicalDetails from './TechnicalDetails';
import FollowUpChat from './FollowUpChat';
import AnomalyCallouts from './AnomalyCallouts';
import Timeline from './Timeline';
import BIInsightsPanel from './BIInsightsPanel';

export default function ResultsDashboard({
  response,
  datasetInfo,
  settings,
  chatMessages,
  onChatMessagesChange,
}) {
  const query = response?.query;
  const plan = response?.metadata?.plan || null;
  const metadata = response?.metadata || null;
  const sql = response?.sql || null;
  const result = response?.result || null;
  const insight = response?.insight || null;
  const warnings = metadata?.validation_warnings || [];
  const intent = plan?.intent || null;
  const kpis = detectKpiMetrics(result);
  const pipelineTime = metadata?.pipeline_time_seconds;
  const hasChart = result?.rows?.length > 0 && result?.columns?.length > 0;

  return (
    <section className="bi-dashboard animate-in">

      {/* ── Query header bar ─────────────────────────────── */}
      <div className="bi-query-bar">
        <div className="min-w-0">
          <p className="bi-query-eyebrow">Your question</p>
          <p className="bi-query-text">{query}</p>
        </div>
        <div className="bi-query-meta">
          {intent && (
            <span className="bi-meta-tag">{intent}</span>
          )}
          {result?.row_count != null && (
            <span className="bi-meta-tag">{result.row_count.toLocaleString()} rows</span>
          )}
          {pipelineTime != null && (
            <span className="bi-meta-tag">{pipelineTime.toFixed(2)}s</span>
          )}
          {metadata?.cache_hit && (
            <span className="bi-meta-tag accent">⚡ cached</span>
          )}
          <button
            type="button"
            onClick={() => window.print()}
            className="no-print bi-export-btn"
          >
            Export Report
          </button>
        </div>
      </div>

      {/* ── Agent Timeline ─────────────────────────────────── */}
      <Timeline agentLogs={response?.agent_logs} />

      {/* ── KPI Cards ─────────────────────────────────────── */}
      {kpis && <KPICard result={result} />}

      {/* ── Top Section: AI Answer + Insights ─────────────── */}
      <div className="bi-top-section">
        {/* AI Answer (left, 60%) */}
        <div className="bi-answer-col">
          {insight && (
            <InsightPanel
              insight={insight}
              autoSpeak={settings.speakInsight && !settings.skipInsight}
            />
          )}
          <AnomalyCallouts result={result} />
        </div>

        {/* Insights panel (right, 40%) */}
        <div className="bi-insights-col">
          <BIInsightsPanel result={result} />
        </div>
      </div>

      {/* ── Primary Chart (full width) ─────────────────────── */}
      {hasChart && (
        <BIChartPanel result={result} intent={intent} query={query || ''} />
      )}

      {/* ── Secondary row: Dataset Summary + Stats ─────────── */}
      <div className="bi-secondary-row">
        <div className="bi-dataset-col" style={{ minWidth: 0 }}>
          <DatasetSummary datasetInfo={datasetInfo} />
        </div>
        {result?.rows?.length > 0 && (
          <div className="bi-stats-col" style={{ minWidth: 0 }}>
            <SecondaryChartOrStats result={result} intent={intent} />
          </div>
        )}
      </div>

      {/* ── Data Table (full width) ────────────────────────── */}
      <ResultTable result={result} fullWidth />

      {/* ── Technical Details ─────────────────────────────── */}
      <TechnicalDetails sql={sql} plan={plan} metadata={metadata} warnings={warnings} />

      {/* ── Follow-Up Chat ────────────────────────────────── */}
      <div className="no-print">
        <FollowUpChat
          query={query}
          sql={sql}
          result={result}
          insight={insight}
          model={settings.model}
          messages={chatMessages}
          onMessagesChange={onChatMessagesChange}
          autoSpeak={settings.speakInsight}
        />
      </div>
    </section>
  );
}

/** Secondary mini-chart showing distribution stats */
function SecondaryChartOrStats({ result, intent }) {
  const { columns = [], rows = [] } = result || {};
  const numericCols = columns.filter(c => rows.some(r => !Number.isNaN(Number(r[c]))));

  if (!numericCols.length) return null;

  const stats = numericCols.slice(0, 3).map(col => {
    const values = rows.map(r => Number(r[col])).filter(v => !Number.isNaN(v));
    const sum = values.reduce((a, b) => a + b, 0);
    const avg = values.length ? sum / values.length : 0;
    const max = Math.max(...values);
    const min = Math.min(...values);
    return { col: col.replace(/_/g, ' '), sum, avg, max, min, count: values.length };
  });

  const fmt = v => {
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
    if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  };

  return (
    <div className="panel-card h-full">
      <h3 className="text-xs font-mono uppercase tracking-widest text-gray-500 mb-4">Numeric Summary</h3>
      <div className="space-y-4">
        {stats.map(s => (
          <div key={s.col} className="bi-stat-block">
            <p className="bi-stat-block-label">{s.col}</p>
            <div className="bi-stat-block-grid">
              <StatMini label="Total" val={fmt(s.sum)} accent />
              <StatMini label="Average" val={fmt(s.avg)} />
              <StatMini label="High" val={fmt(s.max)} />
              <StatMini label="Low" val={fmt(s.min)} />
            </div>
            {/* mini progress bar showing avg/max ratio */}
            <div className="bi-stat-bar-wrap">
              <div className="bi-stat-bar" style={{ width: `${Math.min(100, (s.avg / s.max) * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatMini({ label, val, accent }) {
  return (
    <div>
      <p className="text-[10px] text-gray-600 uppercase tracking-wide">{label}</p>
      <p className={`text-sm font-semibold font-mono ${accent ? 'text-[#c8ff4d]' : 'text-white'}`}>{val}</p>
    </div>
  );
}
