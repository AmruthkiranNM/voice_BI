/**
 * ErrorPanel — Displays error messages
 */
export default function ErrorPanel({ error }) {
  if (!error) return null;

  return (
    <div className="border-l-2 border-red-500 bg-red-500/[0.04] p-5 animate-in">
      <h3 className="text-xs font-data uppercase tracking-wide text-red-400 mb-1">Error</h3>
      <p className="text-sm text-gray-300 leading-relaxed">{error}</p>
    </div>
  );
}
