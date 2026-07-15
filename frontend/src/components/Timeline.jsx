const STEPS = [
  { key: 'Planner Agent', label: 'Planner' },
  { key: 'RAG Retriever Agent', label: 'Retriever' },
  { key: 'SQL Generator Agent', label: 'SQL Writer' },
  { key: 'Validator Agent', label: 'Validator' },
  { key: 'Execution Agent', label: 'Executor' },
  { key: 'Insight Agent', label: 'Insight' },
];

/**
 * Visualizes the multi-agent pipeline that produced a result, using the
 * agent_logs already returned by the orchestrator — no extra requests.
 */
export default function Timeline({ agentLogs }) {
  if (!agentLogs?.length) return null;

  const completed = new Set(agentLogs.map(l => l.agent));
  const skipped = new Set(
    agentLogs.filter(l => l.status?.startsWith('skipped')).map(l => l.agent),
  );

  const getTime = (key) => {
    const logs = agentLogs.filter(l => l.agent === key);
    return logs.length > 0 ? logs[logs.length - 1].timestamp_ms : null;
  };

  return (
    <div className="panel-card">
      <h3 className="text-xs font-data uppercase tracking-wide text-zinc-500 mb-5">Pipeline trace</h3>

      <div className="flex items-start w-full overflow-x-auto pb-1 gap-0">
        {STEPS.map((step, i) => {
          const done = completed.has(step.key);
          const wasSkipped = skipped.has(step.key);
          const time = getTime(step.key);

          return (
            <div key={step.key} className="flex items-center flex-1 min-w-[110px] last:flex-initial">
              <div className="flex flex-col items-center gap-2 relative z-10 w-full">
                <div
                  className={`w-9 h-9 flex items-center justify-center text-xs font-data font-semibold border ${
                    wasSkipped
                      ? 'border-white/10 text-zinc-600 bg-white/[0.02]'
                      : done
                        ? 'border-[#3b82f6]/50 bg-[#3b82f6]/10 text-[#3b82f6]'
                        : 'border-white/10 bg-black/20 text-zinc-600'
                  }`}
                >
                  {i + 1}
                </div>
                <div className="flex flex-col items-center gap-0.5">
                  <span className={`text-[10px] font-data uppercase tracking-wide text-center ${
                    wasSkipped ? 'text-zinc-600' : done ? 'text-zinc-200' : 'text-zinc-600'
                  }`}>
                    {step.label}
                  </span>
                  <span className="text-[9px] text-zinc-600 font-data">
                    {wasSkipped ? 'skipped' : time != null ? `${time.toFixed(0)}ms` : '—'}
                  </span>
                </div>
              </div>

              {i < STEPS.length - 1 && (
                <div className="flex-1 h-px relative -top-4 mx-1">
                  <div className="absolute inset-0 bg-white/10" />
                  <div
                    className={`absolute inset-0 transition-all duration-500 ${
                      done ? 'bg-[#3b82f6]/40' : ''
                    }`}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
