export default function InsightPanel({ insight }) {
  if (!insight) return null;

  return (
    <div className="panel-card w-full bg-gradient-to-br from-gray-900 to-indigo-950/20 border-indigo-500/20">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-400">💡</div>
        <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider">AI Business Insight</h3>
      </div>

      <div className="p-1">
        <p className="text-base text-gray-300 leading-relaxed font-medium">
          {highlightNumbers(insight)}
        </p>
      </div>
    </div>
  );
}

function highlightNumbers(text) {
  const parts = text.split(/(\$?[\d,]+\.?\d*%?)/g);
  return parts.map((part, i) =>
    /^\$?[\d,]+\.?\d*%?$/.test(part)
      ? <span key={i} className="font-bold text-amber-400 bg-amber-500/10 px-1 rounded mx-0.5">{part}</span>
      : part
  );
}
