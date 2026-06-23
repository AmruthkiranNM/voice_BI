import InsightPanel from './InsightPanel';
import ChartPanel from './ChartPanel';
import ResultTable from './ResultTable';
import DatasetSummary from './DatasetSummary';
import ResultStats from './ResultStats';
import KPICard, { detectKpiMetrics } from './KPICard';
import TechnicalDetails from './TechnicalDetails';
import FollowUpChat from './FollowUpChat';
import AnomalyCallouts from './AnomalyCallouts';
import Timeline from './Timeline';

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

  return (
    <section className="w-full animate-in space-y-6 print-report">
      {/* Query header bar */}
      <div className="border-l-2 border-[#c8ff4d] bg-[#c8ff4d]/[0.04] px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs text-[#c8ff4d] font-data uppercase tracking-wide mb-1">Your question</p>
          <p className="text-white font-medium text-base sm:text-lg truncate">{query}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500 shrink-0 font-data">
          {intent && (
            <span className="px-2.5 py-1 bg-white/5 border border-white/10 capitalize">
              {intent}
            </span>
          )}
          {result?.row_count != null && (
            <span>{result.row_count} rows</span>
          )}
          {pipelineTime != null && (
            <span>{pipelineTime.toFixed(2)}s</span>
          )}
          {metadata?.cache_hit && (
            <span className="text-amber-400">cached</span>
          )}
          <button
            type="button"
            onClick={() => window.print()}
            className="no-print px-2.5 py-1 bg-white/5 border border-white/10 hover:border-[#c8ff4d]/40 hover:text-white transition-colors"
          >
            Export report
          </button>
        </div>
      </div>

      <Timeline agentLogs={response?.agent_logs} />

      {/* Top row: answer + dataset context */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 space-y-6">
          {insight && (
            <InsightPanel
              insight={insight}
              autoSpeak={settings.speakInsight && !settings.skipInsight}
            />
          )}
          {kpis && <KPICard result={result} />}
          <AnomalyCallouts result={result} />
          <ResultStats result={result} />
          <div className="no-print">
            <FollowUpChat
              query={query}
              sql={sql}
              result={result}
              insight={insight}
              model={settings.model}
              messages={chatMessages}
              onMessagesChange={onChatMessagesChange}
            />
          </div>
        </div>
        <div className="lg:col-span-4">
          <DatasetSummary datasetInfo={datasetInfo} />
        </div>
      </div>

      {/* Charts — full width */}
      <ChartPanel result={result} intent={intent} fullWidth />

      {/* Data table — full width */}
      <ResultTable result={result} fullWidth />

      <TechnicalDetails
        sql={sql}
        plan={plan}
        metadata={metadata}
        warnings={warnings}
      />
    </section>
  );
}
