const STEPS = [
  { key: 'Planner Agent', label: 'PLANNER', icon: '📋' },
  { key: 'RAG Retriever Agent', label: 'RAG', icon: '🔍' },
  { key: 'SQL Generator Agent', label: 'SQL GEN', icon: '⚡' },
  { key: 'Validator Agent', label: 'VALIDATOR', icon: '🛡️' },
  { key: 'Execution Agent', label: 'EXECUTOR', icon: '▶️' },
  { key: 'Insight Agent', label: 'INSIGHT', icon: '💡' },
];

export default function Timeline({ agentLogs, isLoading }) {
  if (!agentLogs?.length && !isLoading) return null;

  const completed = new Set((agentLogs || []).map(l => l.agent));
  const activeStep = isLoading ? STEPS.find(s => !completed.has(s.key))?.key : null;

  const getTime = (key) => {
    const logs = (agentLogs || []).filter(l => l.agent === key);
    return logs.length > 0 ? logs[logs.length - 1].timestamp_ms : null;
  };

  return (
    <div className="panel-card w-full overflow-hidden">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-8 h-8 rounded-lg bg-gray-800 flex items-center justify-center text-gray-400">⏱️</div>
        <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider">Agent Execution Pipeline</h3>
      </div>

      <div className="flex items-start w-full overflow-x-auto pb-4 hide-scrollbar">
        {STEPS.map((step, i) => {
          const done = completed.has(step.key);
          const active = activeStep === step.key;
          const time = getTime(step.key);

          return (
            <div key={step.key} className="flex items-center flex-1 min-w-[120px]">
              
              <div className="flex flex-col items-center gap-3 relative z-10">
                <div className={`w-12 h-12 rounded-full flex items-center justify-center text-lg border-2 transition-all duration-300
                  ${active ? 'border-indigo-500 bg-indigo-500/20 shadow-[0_0_20px_rgba(99,102,241,0.3)]' 
                    : done ? 'border-green-500/50 bg-green-500/10' 
                    : 'border-gray-800 bg-[#0B1120]'}
                `}>
                  {active ? (
                    <div className="w-5 h-5 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <span className={done ? '' : 'opacity-20 grayscale'}>{step.icon}</span>
                  )}
                </div>

                <div className="flex flex-col items-center gap-1">
                  <span className={`text-[11px] font-bold tracking-wide text-center
                    ${active ? 'text-indigo-400' : done ? 'text-gray-300' : 'text-gray-600'}`}>
                    {step.label}
                  </span>
                  
                  {time != null && (
                    <span className="text-[10px] text-gray-500 font-mono bg-gray-900 px-2 py-0.5 rounded-full border border-gray-800">
                      {time.toFixed(0)}ms
                    </span>
                  )}
                </div>
              </div>

              {i < STEPS.length - 1 && (
                <div className="flex-1 mx-2 h-[2px] rounded-full relative -top-6">
                  <div className="absolute inset-0 bg-gray-800"></div>
                  <div className={`absolute inset-0 transition-all duration-700 ease-out origin-left
                    ${done ? 'bg-green-500/50 scale-x-100' : 'scale-x-0'}`} 
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
