import { TbAlertCircle } from 'react-icons/tb';

/**
 * ErrorPanel — Displays error messages. Same visual language as the
 * error banners in DatasetUpload/DatabaseConnect so an error looks the
 * same everywhere in the app.
 */
export default function ErrorPanel({ error }) {
  if (!error) return null;

  return (
    <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 flex items-start gap-3 animate-in">
      <TbAlertCircle className="w-5 h-5 shrink-0 mt-0.5 text-red-400" />
      <div>
        <h3 className="text-xs font-data uppercase tracking-wide text-red-400 mb-1">Error</h3>
        <p className="text-sm text-zinc-300 leading-relaxed break-words">{error}</p>
      </div>
    </div>
  );
}
