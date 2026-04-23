export default function PlannerPanel({ plan }) {
  if (!plan) return null;

  return (
    <div className="panel-card w-full">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400">📋</div>
          <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider">Planner Agent Output</h3>
        </div>
        {plan.intent && (
          <span className="px-3 py-1 rounded-md bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-bold uppercase tracking-wide">
            Intent: {plan.intent}
          </span>
        )}
      </div>

      <div className="space-y-3 mb-6">
        {plan.steps?.map((step, i) => (
          <div key={i} className="flex items-start gap-4 py-3 px-4 rounded-xl bg-gray-900/50 border border-gray-800">
            <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-400 text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
              {i + 1}
            </span>
            <span className="text-sm text-gray-300 leading-relaxed">{step}</span>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-2 mt-auto pt-4 border-t border-gray-800">
        <span className="text-xs text-gray-500 uppercase tracking-widest mr-2 self-center font-bold">Metadata:</span>
        {plan.metrics?.map((m, i) => (
          <span key={i} className="px-2.5 py-1 rounded-md bg-green-500/10 border border-green-500/20 text-green-400 text-xs font-medium">
            Metric: {m}
          </span>
        ))}
        {plan.grouping && (
          <span className="px-2.5 py-1 rounded-md bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-medium">
            Group by: {plan.grouping}
          </span>
        )}
      </div>
    </div>
  );
}
