import { useState, useCallback, useEffect } from 'react';
import { submitQuery, getDatasets } from './services/api';
import { useQueryHistory } from './hooks/useQueryHistory';

import Header from './components/Header';
import QueryInput, { DEFAULT_SETTINGS } from './components/QueryInput';
import PlannerPanel from './components/PlannerPanel';
import SQLPanel from './components/SQLPanel';
import ResultTable from './components/ResultTable';
import SchemaPanel from './components/SchemaPanel';
import InsightPanel from './components/InsightPanel';
import ChartPanel from './components/ChartPanel';
import Timeline from './components/Timeline';
import ErrorPanel from './components/ErrorPanel';
import DatasetUpload from './components/DatasetUpload';

export default function App() {
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [datasetInfo, setDatasetInfo] = useState({ has_data: false, tables: [], suggestions: [], domain: null });
  const { history, addEntry, clearHistory, removeEntry } = useQueryHistory();

  const refreshDatasets = useCallback(async () => {
    const data = await getDatasets();
    setDatasetInfo(data);
  }, []);

  useEffect(() => { refreshDatasets(); }, [refreshDatasets]);

  const handleUploadSuccess = useCallback((uploadResult) => {
    setDatasetInfo(prev => ({
      ...prev,
      has_data: true,
      domain: uploadResult.domain,
      suggestions: uploadResult.suggestions || [],
      total_tables: uploadResult.total_tables,
    }));
    refreshDatasets();
  }, [refreshDatasets]);

  const handleSubmit = useCallback(async (query) => {
    if (!datasetInfo.has_data) {
      setError('Please upload your business CSV file before asking questions.');
      return;
    }

    setIsLoading(true);
    setError(null);
    setResponse(null);

    try {
      const result = await submitQuery(query, {
        model: settings.model || null,
        cacheMode: settings.cacheMode,
        fastMode: settings.fastMode,
        skipInsight: settings.skipInsight,
      });
      setResponse(result);
      if (result.success) {
        addEntry({
          query,
          rowCount: result.result?.row_count,
          summary: result.insight?.slice(0, 100),
        });
      } else {
        setError(result.error);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [settings, datasetInfo.has_data, addEntry]);

  const plan = response?.metadata?.plan || null;
  const metadata = response?.metadata || null;
  const sql = response?.sql || null;
  const result = response?.result || null;
  const insight = response?.insight || null;
  const agentLogs = response?.agent_logs || [];
  const pipelineTime = metadata?.pipeline_time_seconds || 0;
  const warnings = metadata?.validation_warnings || [];
  const intent = plan?.intent || null;
  const hasData = response && (sql || result?.row_count > 0 || insight);

  return (
    <div className="min-h-screen bg-[#0B1120] text-[#E5E7EB] font-sans selection:bg-indigo-500/30">
      <Header isProcessing={isLoading} />

      <main className="max-w-[1400px] mx-auto px-6 py-10 flex flex-col gap-10">

        {!response && !isLoading && !error && (
          <div className="py-16 text-center max-w-3xl mx-auto flex flex-col items-center gap-6">
            <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-3xl mb-2">
              🎙️
            </div>
            <h2 className="text-4xl md:text-5xl font-extrabold tracking-tight">
              Understand Your Business Data
            </h2>
            <p className="text-lg text-gray-400 leading-relaxed">
              Upload your CSV, then ask questions by typing or speaking. Our AI agents analyze your data and give you clear, actionable business insights — fully on your machine.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 w-full mt-4 text-left">
              {[
                { step: '1', title: 'Upload CSV', desc: 'Sales, customers, inventory — any business spreadsheet' },
                { step: '2', title: 'Ask a Question', desc: 'Type or use your voice to ask what you want to know' },
                { step: '3', title: 'Get Analysis', desc: 'See charts, data tables, and AI-written business insights' },
              ].map(item => (
                <div key={item.step} className="p-4 rounded-xl bg-card border border-border">
                  <span className="text-xs font-bold text-indigo-400 uppercase">Step {item.step}</span>
                  <h3 className="font-bold text-gray-200 mt-1">{item.title}</h3>
                  <p className="text-sm text-gray-500 mt-1">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="max-w-4xl mx-auto w-full z-10 relative">
          <DatasetUpload onUploadSuccess={handleUploadSuccess} />
          <QueryInput
            onSubmit={handleSubmit}
            isLoading={isLoading}
            settings={settings}
            onSettingsChange={setSettings}
            hasDataset={datasetInfo.has_data}
            suggestions={datasetInfo.suggestions}
            history={history}
            onClearHistory={clearHistory}
            onRemoveHistory={removeEntry}
          />
        </div>

        {error && (
          <div className="max-w-4xl mx-auto w-full">
            <ErrorPanel error={error} />
          </div>
        )}

        {isLoading && (
          <div className="w-full max-w-5xl mx-auto flex flex-col gap-6 items-center py-20">
            <div className="w-12 h-12 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
            <p className="text-indigo-400 font-medium animate-pulse">Analyzing your business data...</p>
          </div>
        )}

        {hasData && !isLoading && (
          <div className="flex flex-col gap-8 w-full animate-in fade-in duration-500">

            <div className="flex items-center gap-2 px-1">
              <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">Step 3</span>
              <span className="text-sm font-semibold text-gray-300">Your Analysis</span>
            </div>

            <div className="w-full rounded-2xl border p-5 flex items-center gap-5 shadow-lg bg-emerald-950/30 border-emerald-500/30">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl flex-shrink-0 bg-emerald-500/20">
                {metadata?.cache_hit ? '⚡' : '🦙'}
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-bold mb-1 text-emerald-400">
                  {metadata?.cache_hit ? 'Instant Result from Cache' : 'Analysis Complete'}
                </h3>
                <p className="text-sm text-gray-400">
                  {metadata?.cache_hit
                    ? `Cached result from ${metadata.cached_at_seconds_ago ?? 0}s ago.`
                    : 'Your data was analyzed locally. No information left your computer.'}
                </p>
              </div>
              <div className="hidden md:flex flex-col items-end gap-1 text-xs text-gray-500 font-mono bg-black/20 p-2 rounded-lg">
                <div>Time: <span className="text-emerald-400">{pipelineTime.toFixed(2)}s</span></div>
                <div>Rows: <span className="text-emerald-400">{result?.row_count}</span></div>
              </div>
            </div>

            <Timeline agentLogs={agentLogs} isLoading={false} />

            <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start">
              <div className="xl:col-span-7 flex flex-col gap-8 w-full min-w-0">
                <InsightPanel insight={insight} autoSpeak={settings.speakInsight && !settings.skipInsight} />
                <ChartPanel result={result} intent={intent} />
                <ResultTable result={result} />
              </div>

              <div className="xl:col-span-5 flex flex-col gap-8 w-full min-w-0">
                <PlannerPanel plan={plan} />
                <SQLPanel sql={sql} warnings={warnings} />
                <SchemaPanel metadata={metadata} />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
