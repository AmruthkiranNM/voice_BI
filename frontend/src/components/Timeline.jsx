const STEPS = [
  { key: 'Planner Agent', label: 'PLANNER', icon: '📋' },
  { key: 'RAG Retriever Agent', label: 'RETRIEVER', icon: '🔍' },
  { key: 'SQL Generator Agent', label: 'SQL WRITER', icon: '⚡' },
  { key: 'Validator Agent', label: 'VALIDATOR', icon: '🛡️' },
  { key: 'Execution Agent', label: 'EXECUTOR', icon: '▶️' },
  { key: 'Insight Agent', label: 'INSIGHTS', icon: '💡' },
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
    <div className="panel-card w-full overflow-hidden border border-white/5 bg-gray-950/20 backdrop-blur-md rounded-3xl p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-8 h-8 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-xs shadow-inner">
          ⏱️
        </div>
        <h3 className="text-xs font-bold text-white uppercase tracking-widest">Agent Execution Graph</h3>
      </div>

      <div className="flex items-start w-full overflow-x-auto pb-2 scrollbar-none gap-2 md:gap-0">
        {STEPS.map((step, i) => {
          const done = completed.has(step.key);
          const active = activeStep === step.key;
          const time = getTime(step.key);

          return (
            <div key={step.key} className="flex items-center flex-1 min-w-[130px] last:flex-initial">
              
              <div className="flex flex-col items-center gap-2 relative z-10">
                <div className={`w-11 h-11 rounded-2xl flex items-center justify-center text-sm border transition-all duration-300
                  ${active 
                    ? 'border-indigo-400 bg-indigo-500/20 shadow-[0_0_20px_rgba(99,102,241,0.25)]' 
                    : done 
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.05)]' 
                      : 'border-white/5 bg-[#0b0f19]/80'}
                `}>
                  {active ? (
                    <div className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <span className={done ? '' : 'opacity-20 grayscale'}>{step.icon}</span>
                  )}
                </div>

                <div className="flex flex-col items-center gap-1">
                  <span className={`text-[10px] font-bold tracking-widest text-center
                    ${active ? 'text-indigo-400' : done ? 'text-gray-200' : 'text-gray-600'}`}>
                    {step.label}
                  </span>
                  
                  {time != null && (
                    <span className="text-[9px] text-gray-400 font-bold font-mono bg-white/5 border border-white/5 px-2 py-0.5 rounded-md">
                      {time.toFixed(0)}ms
                    </span>
                  )}
                </div>
              </div>

              {i < STEPS.length - 1 && (
                <div className="flex-1 mx-2 h-[1px] relative -top-6">
                  <div className="absolute inset-0 bg-white/5"></div>
                  <div className={`absolute inset-0 transition-all duration-500 ease-out origin-left
                    ${done ? 'bg-gradient-to-r from-emerald-500/40 to-indigo-500/40 scale-x-100' : 'scale-x-0'}`} 
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
