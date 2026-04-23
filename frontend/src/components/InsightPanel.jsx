/**
 * InsightPanel — AI-generated business insight
 */
export default function InsightPanel({ insight }) {
  if (!insight) return null;

  return (
    <div className="bg-card border border-border rounded-2xl p-6 fade-up-2
                    hover:border-border-hover transition-colors duration-200">
      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <span className="text-lg">💡</span>
        <h3 className="text-sm font-bold text-text-primary uppercase tracking-wide">
          AI Insight
        </h3>
      </div>

      {/* Insight content */}
      <div className="p-5 rounded-xl bg-gradient-to-br from-amber/5 to-indigo/5
                      border border-amber/10">
        <p className="text-sm text-text-primary leading-7">
          {highlightNumbers(insight)}
        </p>
      </div>
    </div>
  );
}

/** Highlight numbers in text with amber color */
function highlightNumbers(text) {
  const parts = text.split(/(\$?[\d,]+\.?\d*%?)/g);
  return parts.map((part, i) =>
    /^\$?[\d,]+\.?\d*%?$/.test(part)
      ? <span key={i} className="font-bold text-amber">{part}</span>
      : part
  );
}
