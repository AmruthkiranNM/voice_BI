/**
 * PlannerPanel — Shows planner agent output
 * Displays steps, intent, metrics, and grouping
 */
export default function PlannerPanel({ plan }) {
  if (!plan) return null;

  return (
    <div className="bg-card border border-border rounded-2xl p-6 fade-up-1
                    hover:border-border-hover transition-colors duration-200">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <span className="text-lg">📋</span>
          <h3 className="text-sm font-bold text-text-primary uppercase tracking-wide">
            Planner Output
          </h3>
        </div>
        {plan.intent && (
          <span className="px-3 py-1 rounded-lg bg-indigo/10 border border-indigo/20
                         text-indigo text-xs font-bold capitalize">
            {plan.intent}
          </span>
        )}
      </div>

      {/* Steps */}
      {plan.steps?.length > 0 && (
        <div className="space-y-2.5 mb-5">
          {plan.steps.map((step, i) => (
            <div key={i} className="flex items-start gap-3 py-2.5 px-4 rounded-xl bg-bg/60">
              <span className="w-6 h-6 rounded-lg bg-indigo/15 text-indigo text-[10px]
                             font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                {i + 1}
              </span>
              <span className="text-sm text-text-secondary leading-relaxed">{step}</span>
            </div>
          ))}
        </div>
      )}

      {/* Tags row */}
      <div className="flex flex-wrap gap-2">
        {plan.metrics?.map((m, i) => (
          <span key={i} className="px-2.5 py-1 rounded-lg bg-green/8 border border-green/15
                                  text-green text-[11px] font-semibold">
            {m}
          </span>
        ))}
        {plan.grouping && (
          <span className="px-2.5 py-1 rounded-lg bg-amber/8 border border-amber/15
                         text-amber text-[11px] font-semibold">
            Group by: {plan.grouping}
          </span>
        )}
        {plan.filters?.time_range && (
          <span className="px-2.5 py-1 rounded-lg bg-cyan/8 border border-cyan/15
                         text-cyan text-[11px] font-semibold">
            {plan.filters.time_range}
          </span>
        )}
      </div>
    </div>
  );
}
