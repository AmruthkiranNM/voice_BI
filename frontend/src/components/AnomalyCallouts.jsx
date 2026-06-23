import { useMemo } from 'react';
import { buildCallouts } from '../utils/resultAnalytics';

/**
 * Plain-English callouts (period change, outliers, correlation) computed
 * directly from the result data — not the LLM — so they're always accurate
 * even on a small local model, and cost zero extra latency.
 */
export default function AnomalyCallouts({ result }) {
  const callouts = useMemo(() => buildCallouts(result), [result]);
  if (!callouts.length) return null;

  return (
    <div className="panel-card">
      <h3 className="text-xs font-data uppercase tracking-wide text-gray-500 mb-4">Worth noting</h3>
      <ul className="space-y-2.5">
        {callouts.map((c, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm text-gray-300 leading-relaxed">
            <span
              className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${
                c.type === 'positive' ? 'bg-[#c8ff4d]' : c.type === 'negative' ? 'bg-red-400' : 'bg-gray-500'
              }`}
            />
            {c.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
