/**
 * ErrorPanel — Displays error messages
 */
export default function ErrorPanel({ error }) {
  if (!error) return null;

  return (
    <div className="bg-card border border-red/30 rounded-2xl p-6 fade-up">
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 rounded-xl bg-red/10 flex items-center justify-center text-lg flex-shrink-0">
          ⚠️
        </div>
        <div>
          <h3 className="text-sm font-bold text-red mb-1">Error</h3>
          <p className="text-sm text-text-secondary leading-relaxed">{error}</p>
        </div>
      </div>
    </div>
  );
}
