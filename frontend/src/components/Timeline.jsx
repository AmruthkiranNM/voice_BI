import { useMemo } from 'react';

const STEPS = [
  { key: 'Planner Agent', label: 'Planner', weight: 0.8 },
  { key: 'RAG Retriever Agent', label: 'Retriever', weight: 0.9 },
  { key: 'SQL Generator Agent', label: 'SQL Writer', weight: 1.5 },
  { key: 'Validator Agent', label: 'Validator', weight: 1.0 },
  { key: 'Execution Agent', label: 'Executor', weight: 1.3 },
  { key: 'Insight Agent', label: 'Insight', weight: 1.2 },
];

/** Splits totalMs across steps using their weights, jittered ±20% like the AI processing loader, renormalized so it still sums to totalMs. */
function randomizedStepTimes(totalMs) {
  const jittered = STEPS.map(s => s.weight * (0.8 + Math.random() * 0.4));
  const sum = jittered.reduce((a, b) => a + b, 0);
  return jittered.map(w => (w / sum) * totalMs);
}

/**
 * Visualizes the multi-agent pipeline that produced a result, using the
 * agent_logs already returned by the orchestrator for completion/skip state,
 * with per-step timings randomized (like the AI processing loader) against
 * the real total pipeline time rather than raw per-agent timestamps.
 */
export default function Timeline({ agentLogs, pipelineTime }) {
  if (!agentLogs?.length) return null;

  const completed = new Set(agentLogs.map(l => l.agent));
  const skipped = new Set(
    agentLogs.filter(l => l.status?.startsWith('skipped')).map(l => l.agent),
  );

  const totalMs = pipelineTime != null ? pipelineTime * 1000 : null;
  const randomTimes = useMemo(
    () => (totalMs != null ? randomizedStepTimes(totalMs) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [agentLogs],
  );

  const getTime = (key, i) => {
    if (randomTimes) return randomTimes[i];
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
          const time = getTime(step.key, i);

          return (
            <div key={step.key} className="flex items-center flex-1 min-w-[110px] last:flex-initial">
              <div className="flex flex-col items-center gap-2 relative z-10 w-full">
                <div
                  className={`w-9 h-9 flex items-center justify-center text-xs font-data font-semibold border ${
                    wasSkipped
                      ? 'border-black/10 text-zinc-600 bg-black/[0.02]'
                      : done
                        ? 'border-[#9C4A2A]/50 bg-[#9C4A2A]/10 text-[#9C4A2A]'
                        : 'border-black/10 bg-black/[0.03] text-zinc-600'
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
                  <div className="absolute inset-0 bg-black/10" />
                  <div
                    className={`absolute inset-0 transition-all duration-500 ${
                      done ? 'bg-[#9C4A2A]/40' : ''
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
