/**
 * Timeline — Horizontal agent pipeline tracker
 * Shows: Planner -> RAG -> SQL -> Validator -> Execution -> Insight
 */

const STEPS = [
  { key: 'Planner Agent', label: 'Planner', icon: '📋' },
  { key: 'RAG Retriever Agent', label: 'RAG', icon: '🔍' },
  { key: 'SQL Generator Agent', label: 'SQL Gen', icon: '⚡' },
  { key: 'Validator Agent', label: 'Validator', icon: '🛡️' },
  { key: 'Execution Agent', label: 'Executor', icon: '▶️' },
  { key: 'Insight Agent', label: 'Insight', icon: '💡' },
];

export default function Timeline({ agentLogs, isLoading, pipelineTime }) {
  if (!agentLogs?.length && !isLoading) return null;

  const completed = new Set((agentLogs || []).map(l => l.agent));
  const activeStep = isLoading ? STEPS.find(s => !completed.has(s.key))?.key : null;

  const getTime = (key) => {
    const logs = (agentLogs || []).filter(l => l.agent === key);
    return logs.length > 0 ? logs[logs.length - 1].timestamp_ms : null;
  };

  return (
    <div className="bg-card border border-border rounded-2xl p-6 fade-up">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <span className="text-lg">⏱️</span>
          <h3 className="text-sm font-bold text-text-primary uppercase tracking-wide">
            Agent Execution Pipeline
          </h3>
        </div>
        {pipelineTime > 0 && (
          <span className="text-xs text-text-secondary font-mono bg-bg px-3 py-1 rounded-lg border border-border">
            {pipelineTime.toFixed(2)}s total
          </span>
        )}
      </div>

      {/* Horizontal timeline */}
      <div className="flex items-start">
        {STEPS.map((step, i) => {
          const done = completed.has(step.key);
          const active = activeStep === step.key;
          const time = getTime(step.key);

          return (
            <div key={step.key} className="flex items-start flex-1 min-w-0">
              {/* Step */}
              <div className="flex flex-col items-center gap-2 flex-1">
                {/* Circle */}
                <div className={`w-11 h-11 rounded-full flex items-center justify-center text-base
                  border-2 transition-all duration-500
                  ${active
                    ? 'border-indigo bg-indigo/20 shadow-[0_0_16px_rgba(99,102,241,0.4)]'
                    : done
                      ? 'border-green/50 bg-green/10'
                      : 'border-border bg-bg'
                  }`}
                >
                  {active ? (
                    <div className="w-4 h-4 border-2 border-indigo border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <span className={done ? '' : 'opacity-30'}>{step.icon}</span>
                  )}
                </div>

                {/* Label */}
                <span className={`text-[11px] font-bold text-center leading-tight
                  ${active ? 'text-indigo' : done ? 'text-text-secondary' : 'text-text-muted'}`}>
                  {step.label}
                </span>

                {/* Timing */}
                {time != null && (
                  <span className="text-[9px] text-text-muted font-mono bg-bg px-1.5 py-0.5 rounded">
                    {time.toFixed(0)}ms
                  </span>
                )}
              </div>

              {/* Connector line */}
              {i < STEPS.length - 1 && (
                <div className={`h-[2px] w-full mt-5 mx-[-4px] transition-colors duration-500
                  ${done ? 'bg-green/40' : 'bg-border'}`}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
