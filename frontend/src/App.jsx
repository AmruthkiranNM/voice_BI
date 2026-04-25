import { useState, useCallback } from 'react';
import { submitQuery } from './services/api';

import Header from './components/Header';
import QueryInput from './components/QueryInput';
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
  const [llmMode, setLlmMode] = useState('ollama');
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);

  const handleSubmit = useCallback(async (query) => {
    setIsLoading(true);
    setError(null);
    setResponse(null);

    try {
      const result = await submitQuery(query, llmMode);
      setResponse(result);
      if (!result.success) setError(result.error);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [llmMode]);

  const plan = response?.metadata?.plan || null;
  const metadata = response?.metadata || null;
  const sql = response?.sql || null;
  const result = response?.result || null;
  const insight = response?.insight || null;
  const agentLogs = response?.agent_logs || [];
  const pipelineTime = metadata?.pipeline_time_seconds || 0;
  const warnings = metadata?.validation_warnings || [];
  const intent = plan?.intent || null;
  const actualMode = response?.llm_mode || 'ollama';
  const hasData = response && (sql || result?.row_count > 0 || insight);

  return (
    <div className="min-h-screen bg-[#0B1120] text-[#E5E7EB] font-sans selection:bg-indigo-500/30">
      <Header llmMode={llmMode} onModeChange={setLlmMode} isProcessing={isLoading} />

      <main className="max-w-[1400px] mx-auto px-6 py-10 flex flex-col gap-10">
        
        {/* Hero / Welcome */}
        {!response && !isLoading && !error && (
          <div className="py-24 text-center max-w-3xl mx-auto flex flex-col items-center gap-6">
            <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-3xl mb-4">
              ✨
            </div>
            <h2 className="text-4xl md:text-5xl font-extrabold tracking-tight">
              Agentic Business Intelligence
            </h2>
            <p className="text-lg text-gray-400 leading-relaxed">
              Ask natural language questions about your business data. Our multi-agent AI pipeline will retrieve schema, generate SQL, and visualize the results instantly.
            </p>
          </div>
        )}

        {/* Search Bar */}
        <div className="max-w-4xl mx-auto w-full z-10 relative">
          <DatasetUpload />
          <QueryInput onSubmit={handleSubmit} isLoading={isLoading} />
        </div>

        {error && (
          <div className="max-w-4xl mx-auto w-full">
            <ErrorPanel error={error} />
          </div>
        )}

        {/* Loading State */}
        {isLoading && (
          <div className="w-full max-w-5xl mx-auto flex flex-col gap-6 items-center py-20">
            <div className="w-12 h-12 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
            <p className="text-indigo-400 font-medium animate-pulse">Running Agentic Pipeline...</p>
          </div>
        )}

        {/* Dashboard Results */}
        {hasData && !isLoading && (
          <div className="flex flex-col gap-8 w-full animate-in fade-in duration-500">
            
            {/* VERY CLEAR API MODE INDICATOR */}

            <div className={`w-full rounded-2xl border p-5 flex items-center gap-5 shadow-lg
              ${actualMode === 'gemini' 
                ? 'bg-indigo-950/40 border-indigo-500/30 shadow-indigo-500/10' 
                : actualMode === 'ollama'
                ? 'bg-emerald-950/30 border-emerald-500/30 shadow-emerald-500/5'
                : 'bg-amber-950/30 border-amber-500/30 shadow-amber-500/5'}`}
            >
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-2xl flex-shrink-0
                ${actualMode === 'gemini' ? 'bg-indigo-500/20' : actualMode === 'ollama' ? 'bg-emerald-500/20' : 'bg-amber-500/20'}`}>
                {actualMode === 'gemini' ? '🧠' : actualMode === 'ollama' ? '🦙' : '🤖'}
              </div>
              <div className="flex-1">
                <h3 className={`text-lg font-bold mb-1 ${actualMode === 'gemini' ? 'text-indigo-400' : actualMode === 'ollama' ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {actualMode === 'gemini' ? 'Powered by Google Gemini (Live AI)' : actualMode === 'ollama' ? 'Powered by Local Ollama (Qwen)' : 'Running in Mock Mode (Rule-Based)'}
                </h3>
                <p className="text-sm text-gray-400">
                  {actualMode === 'gemini' 
                    ? 'The query planner, SQL generator, and insight agents are using real LLM calls.' 
                    : actualMode === 'ollama'
                    ? 'Running fully locally using your Ollama instance. No internet connection required.'
                    : 'No API key detected. The system is using the fallback mock engine to demonstrate the pipeline.'}

                </p>
              </div>
              <div className="hidden md:flex flex-col items-end gap-1 text-xs text-gray-500 font-mono bg-black/20 p-2 rounded-lg">
                <div>Pipeline Time: <span className="text-emerald-400">{pipelineTime.toFixed(2)}s</span></div>
                {metadata?.execution_time_ms && <div>DB Query: <span className="text-emerald-400">{metadata.execution_time_ms.toFixed(1)}ms</span></div>}
                <div>Rows Found: <span className="text-emerald-400">{result?.row_count}</span></div>
              </div>
            </div>

            {/* Timeline spans full width */}
            <Timeline agentLogs={agentLogs} isLoading={false} />

            {/* 2-Column Grid Layout (Prevents overlapping) */}
            <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start">
              
              {/* LEFT COLUMN - Primary Content (7 columns) */}
              <div className="xl:col-span-7 flex flex-col gap-8 w-full min-w-0">
                <PlannerPanel plan={plan} />
                <SQLPanel sql={sql} warnings={warnings} />
                <ResultTable result={result} />
              </div>

              {/* RIGHT COLUMN - Context & Visuals (5 columns) */}
              <div className="xl:col-span-5 flex flex-col gap-8 w-full min-w-0">
                <InsightPanel insight={insight} />
                <ChartPanel result={result} intent={intent} />
                <SchemaPanel metadata={metadata} />
              </div>

            </div>
          </div>
        )}
      </main>
    </div>
  );
}
