import { useState } from 'react';

export default function TechnicalDetails({ sql, plan, metadata, warnings }) {
  const [open, setOpen] = useState(false);

  if (!sql && !plan) return null;

  return (
    <div className="border-t border-white/8 pt-4">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="text-xs text-zinc-400 hover:text-white transition-colors font-data"
      >
        {open ? '− Hide technical details' : '+ Technical details'}
      </button>

      {open && (
        <div className="mt-3 space-y-3 text-xs font-data text-zinc-500">
          {metadata?.pipeline_time_seconds != null && (
            <p>Response time: {metadata.pipeline_time_seconds.toFixed(2)}s</p>
          )}
          {plan?.intent && (
            <div className="p-3 bg-black/20 border border-white/10">
              <p className="text-zinc-600 mb-1">Plan</p>
              <pre className="whitespace-pre-wrap text-zinc-400">{JSON.stringify(plan, null, 2)}</pre>
            </div>
          )}
          {sql && (
            <div className="p-3 bg-black/20 border border-white/10 overflow-x-auto">
              <p className="text-zinc-600 mb-1">SQL</p>
              <pre className="text-zinc-400">{sql}</pre>
            </div>
          )}
          {warnings?.length > 0 && (
            <div className="text-amber-500/80">
              {warnings.map((w, i) => <p key={i}>{w}</p>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
