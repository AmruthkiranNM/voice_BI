/**
 * App.jsx — Main Dashboard
 * 
 * Agentic AI-Based Business Intelligence System
 * Layout: Header → Query → 2-column grid → Timeline
 */

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

export default function App() {
  const [llmMode, setLlmMode] = useState('mock');
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

  // Extract data
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
    <div className="min-h-screen bg-bg-primary">
      {/* ── Header ── */}
      <Header llmMode={llmMode} onModeChange={setLlmMode} isProcessing={isLoading} />

      {/* ── Content ── */}
      <main className="max-w-[1440px] mx-auto px-6 py-5 space-y-5">
        
        {/* Welcome state */}
        {!response && !isLoading && !error && (
          <div className="text-center py-16 anim-fade">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 border border-accent/20 mb-5">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              <span className="text-[11px] font-medium text-accent">System Ready</span>
            </div>
            <h2 className="text-2xl font-bold text-text mb-2">Ask Your Business Data Anything</h2>
            <p className="text-sm text-text-muted max-w-md mx-auto">
              Natural language queries processed through a multi-agent AI pipeline with RAG-augmented schema retrieval.
            </p>

            {/* Mini architecture */}
            <div className="flex items-center justify-center gap-2 mt-8">
              {['Query', 'Planner', 'RAG', 'SQL', 'Validator', 'Execute', 'Insight'].map((s, i, a) => (
                <div key={s} className="flex items-center gap-2">
                  <span className="px-2.5 py-1 rounded-md bg-bg-card border border-border text-[10px] font-medium text-text-dim">{s}</span>
                  {i < a.length - 1 && <span className="text-border text-xs">→</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Query Input */}
        <QueryInput onSubmit={handleSubmit} isLoading={isLoading} />

        {/* Error */}
        {error && <ErrorPanel error={error} />}

        {/* Loading skeleton */}
        {isLoading && (
          <div className="space-y-4 anim-fade">
            <div className="card p-4">
              <div className="h-3 w-24 rounded shimmer-bg mb-3" />
              <div className="grid grid-cols-6 gap-3">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className="flex flex-col items-center gap-2 py-3">
                    <div className="w-9 h-9 rounded-full shimmer-bg" />
                    <div className="h-2 w-10 rounded shimmer-bg" />
                  </div>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-5 gap-4">
              <div className="col-span-3 space-y-4">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="card p-4">
                    <div className="h-3 w-28 rounded shimmer-bg mb-3" />
                    <div className="space-y-2">
                      <div className="h-6 rounded shimmer-bg" />
                      <div className="h-6 rounded shimmer-bg" />
                    </div>
                  </div>
                ))}
              </div>
              <div className="col-span-2 space-y-4">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="card p-4">
                    <div className="h-3 w-20 rounded shimmer-bg mb-3" />
                    <div className="h-24 rounded shimmer-bg" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── Results Dashboard ── */}
        {hasData && !isLoading && (
          <div className="space-y-5">
            {/* Pipeline Timeline — full width */}
            <Timeline agentLogs={agentLogs} isLoading={false} pipelineTime={pipelineTime} />

            {/* 2-Column Grid: Left 60% / Right 40% */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
              
              {/* LEFT — 60% (3 of 5 cols) */}
              <div className="lg:col-span-3 space-y-5">
                <PlannerPanel plan={plan} />
                <SQLPanel sql={sql} warnings={warnings} />
                <ResultTable result={result} />
              </div>

              {/* RIGHT — 40% (2 of 5 cols) */}
              <div className="lg:col-span-2 space-y-5">
                <SchemaPanel metadata={metadata} />
                <InsightPanel insight={insight} />
                <ChartPanel result={result} intent={intent} />
              </div>
            </div>

            {/* Footer metadata */}
            <div className="flex items-center justify-center gap-6 py-3 text-[10px] text-text-muted">
              <span>Pipeline: <strong className="text-text-dim">{pipelineTime.toFixed(2)}s</strong></span>
              {metadata?.execution_time_ms != null && (
                <span>SQL: <strong className="text-text-dim">{metadata.execution_time_ms.toFixed(1)}ms</strong></span>
              )}
              {result?.row_count != null && (
                <span>Rows: <strong className="text-text-dim">{result.row_count}</strong></span>
              )}
              <span>LLM: <strong className="text-accent">{response?.llm_mode || llmMode}</strong></span>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-border mt-6">
        <div className="max-w-[1440px] mx-auto px-6 py-3 flex justify-between text-[10px] text-text-muted">
          <span>Agentic AI Business Intelligence — Final Year Project</span>
          <span>Multi-Agent RAG Architecture</span>
        </div>
      </footer>
    </div>
  );
}
