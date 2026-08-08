import { useState, useEffect } from 'react';
import { TbSearch } from 'react-icons/tb';
import InsightPanel from './InsightPanel';
import BIChartPanel from './BIChartPanel';
import ResultTable from './ResultTable';
import DatasetSummary from './DatasetSummary';
import TechnicalDetails from './TechnicalDetails';
import FollowUpChat from './FollowUpChat';
import AnomalyCallouts from './AnomalyCallouts';
import Timeline from './Timeline';
import BIInsightsPanel from './BIInsightsPanel';
import InvestigationTrail from './InvestigationTrail';
import { resolveVisualizationSpec } from '../utils/semanticClassifier';
import { showToast } from '../utils/toast';
import { investigateQuery } from '../services/api';

export default function ResultsDashboard({
  response,
  datasetInfo,
  settings,
  chatMessages,
  onChatMessagesChange,
  sourceLabel,
  fakePipelineSeconds,
}) {
  const query = response?.query;
  const plan = response?.metadata?.plan || null;
  const metadata = response?.metadata || null;
  const sql = response?.sql || null;
  const result = response?.result || null;
  const insight = response?.insight || null;
  const warnings = metadata?.validation_warnings || [];
  const intent = plan?.intent || null;
  const pipelineTime = fakePipelineSeconds ?? metadata?.pipeline_time_seconds;
  const hasChart = result?.rows?.length > 0 && result?.columns?.length > 0;

  // Row-click drill-through: turn a clicked table row into a follow-up
  // question for the AI Data Analyst chat below, instead of re-running the
  // full SQL pipeline for a single row's worth of context.
  const [pendingQuestion, setPendingQuestion] = useState(null);
  const handleRowDrill = (row, cols) => {
    const parts = cols.slice(0, 4).map(c => `${c.replace(/_/g, ' ')}: ${row[c]}`);
    setPendingQuestion(`Tell me more about this row — ${parts.join(', ')}.`);
  };

  // Autonomous multi-hop drill-down — the system decides its own follow-up
  // questions to explain *why* this result looks the way it does, instead
  // of the user having to ask each step manually.
  const [investigation, setInvestigation] = useState(null);
  const [isInvestigating, setIsInvestigating] = useState(false);
  useEffect(() => { setInvestigation(null); setIsInvestigating(false); }, [query]);

  const handleInvestigate = async () => {
    setIsInvestigating(true);
    try {
      const outcome = await investigateQuery(query, {
        sql,
        result,
        model: settings?.model,
        tableNames: datasetInfo?.tableNames,
      });
      setInvestigation(outcome);
    } catch (err) {
      showToast(err.message || 'Investigation failed.');
    } finally {
      setIsInvestigating(false);
    }
  };

  return (
    <section className="bi-dashboard animate-in">

      {/* ── Header bar — small-caps eyebrow, serif heading, pill tags, no card ── */}
      <div className="bi-header-bar">
        <div className="min-w-0">
          <p className="bi-header-eyebrow">Analysis Workspace{sourceLabel ? ` / ${sourceLabel}` : ''}</p>
          <h2 className="bi-header-title">{query}</h2>
        </div>
        <div className="bi-header-tags">
          {intent && <span className="bi-tag">{intent}</span>}
          {result?.row_count != null && (
            <span className="bi-tag">{result.row_count.toLocaleString()} rows</span>
          )}
          {pipelineTime != null && (
            <span className="bi-tag">{pipelineTime.toFixed(2)}s</span>
          )}
          {metadata?.cache_hit && (
            <span className="bi-tag accent">Cached</span>
          )}
          <button
            type="button"
            onClick={() => { showToast('Export started — check your downloads or print dialog'); window.print(); }}
            className="no-print bi-export-btn"
          >
            Export
          </button>
        </div>
      </div>

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
          {insight && !investigation && !isInvestigating && (
            <button
              type="button"
              onClick={handleInvestigate}
              className="no-print flex items-center gap-1.5 text-xs font-medium text-[#9C4A2A] hover:underline"
            >
              <TbSearch className="w-3.5 h-3.5" />
              Investigate further — why is this the case?
            </button>
          )}
          {(isInvestigating || investigation) && (
            <InvestigationTrail investigation={investigation} isLoading={isInvestigating} />
          )}
          <AnomalyCallouts result={result} />
        </div>

        {/* Insights panel (right, 40%) */}
        <div className="bi-insights-col">
          <BIInsightsPanel result={result} intent={intent} query={query} />
        </div>
      </div>

      {/* ── Follow-Up Chat ────────────────────────────────── */}
      <div id="followup-chat" className="no-print mt-8 mb-8">
        <FollowUpChat
          query={query}
          sql={sql}
          result={result}
          insight={insight}
          model={settings.model}
          tableName={datasetInfo?.tableName}
          tableNames={datasetInfo?.tableNames}
          messages={chatMessages}
          onMessagesChange={onChatMessagesChange}
          autoSpeak={settings.speakInsight}
          pendingQuestion={pendingQuestion}
          onPendingQuestionHandled={() => setPendingQuestion(null)}
        />
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
            <SecondaryChartOrStats result={result} intent={intent} query={query} />
          </div>
        )}
      </div>

      {/* ── Data Table (full width) ────────────────────────── */}
      <ResultTable
        result={result}
        fullWidth
        onRowDrill={(row, cols) => {
          handleRowDrill(row, cols);
          document.getElementById('followup-chat')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }}
      />


      {/* ── Agent Timeline ─────────────────────────────────── */}
      <Timeline agentLogs={response?.agent_logs} pipelineTime={pipelineTime} />

      {/* ── Technical Details ─────────────────────────────── */}
      <TechnicalDetails sql={sql} plan={plan} metadata={metadata} warnings={warnings} />

      {/* ── Footer trace ──────────────────────────────────── */}
      <FooterTrace agentLogs={response?.agent_logs} pipelineTime={pipelineTime} />

    </section>
  );
}

/** Muted, centered, one-line summary of the pipeline that produced this result. */
function FooterTrace({ agentLogs, pipelineTime }) {
  if (!agentLogs?.length) return null;
  const steps = agentLogs
    .filter(l => !l.status?.startsWith('skipped'))
    .map(l => l.agent.replace(' Agent', '').replace('RAG Retriever', 'Retriever').replace('SQL Generator', 'SQL Writer').replace('Execution', 'Executor'));
  const unique = [...new Set(steps)];
  return (
    <p className="text-center text-[11px] font-data text-zinc-500 pt-2">
      {unique.join(' → ')}
      {pipelineTime != null && ` — ${pipelineTime.toFixed(2)}s total`}
    </p>
  );
}

/** Secondary mini-chart showing distribution stats */
function SecondaryChartOrStats({ result, intent, query }) {
  const { columns = [], rows = [] } = result || {};
  const spec = resolveVisualizationSpec(result, intent, query);
  let numericCols = columns.filter(c => rows.some(r => !Number.isNaN(Number(r[c]))));
  
  if (spec && spec.excludedFields) {
    numericCols = numericCols.filter(c => !spec.excludedFields.includes(c));
  }

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
    <div className="panel-card h-full flex flex-col justify-between">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-5">Numeric Summary</h3>
        <div className="space-y-5">
          {stats.map(s => (
            <div key={s.col} className="bi-stat-block">
              <p className="bi-stat-block-label truncate">{s.col}</p>
              <div className="bi-stat-block-grid">
                <StatMini label="Total" val={fmt(s.sum)} accent />
                <StatMini label="Average" val={fmt(s.avg)} />
                <StatMini label="High" val={fmt(s.max)} />
                <StatMini label="Low" val={fmt(s.min)} />
              </div>
              {/* mini progress bar showing avg/max ratio */}
              <div className="bi-stat-bar-wrap mt-2">
                <div className="bi-stat-bar" style={{ width: `${Math.min(100, (s.avg / s.max) * 100)}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatMini({ label, val, accent }) {
  return (
    <div className="bg-black/[0.02] rounded-md p-2 border border-black/5">
      <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-0.5">{label}</p>
      <p className={`text-sm font-semibold font-mono ${accent ? 'text-blue-400' : 'text-zinc-100'}`}>{val}</p>
    </div>
  );
}
