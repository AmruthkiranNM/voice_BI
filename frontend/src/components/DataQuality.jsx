import { TbAlertTriangle, TbCheck, TbAlertCircle, TbInfoCircle } from 'react-icons/tb';

export default function DataQuality({ quality }) {
  if (!quality) return null;

  const { score, issue_count, issues } = quality;

  // Determine overall status color — thresholds/colors match the compact
  // DataQuality score badge shown during upload (DatasetUpload.jsx) so the
  // same score always reads as the same severity throughout the app.
  let statusColor = 'text-[#3E7A4D]';
  let bgGlow = 'bg-[#3E7A4D]/10';
  let borderColor = 'border-[#3E7A4D]/20';
  if (score < 60) {
    statusColor = 'text-red-400';
    bgGlow = 'bg-red-500/10';
    borderColor = 'border-red-500/20';
  } else if (score < 85) {
    statusColor = 'text-amber-400';
    bgGlow = 'bg-amber-500/10';
    borderColor = 'border-amber-500/20';
  }

  return (
    <div className={`glass-panel p-6 rounded-2xl border ${borderColor} animate-in`}>
      <div className="flex items-start justify-between mb-6">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
            <svg stroke="currentColor" fill="none" strokeWidth="2" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" className={`w-4 h-4 ${statusColor}`} xmlns="http://www.w3.org/2000/svg"><path d="M9 12l2 2l4 -4"></path><path d="M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0 -18z"></path></svg>
            Data Quality Report
          </h3>
          <p className="text-zinc-400 text-xs mt-1">
            {issue_count === 0 
              ? 'Your data looks clean and ready for analysis.' 
              : `Found ${issue_count} potential issue${issue_count > 1 ? 's' : ''} in your dataset.`}
          </p>
        </div>
        <div className={`flex items-center justify-center w-12 h-12 rounded-full ${bgGlow} border ${borderColor}`}>
          <span className={`text-xl font-bold ${statusColor}`}>{score}</span>
        </div>
      </div>

      {issues?.length > 0 && (
        <div className="space-y-3">
          {issues.map((issue, idx) => (
            <div key={idx} className="flex gap-3 p-3 rounded-lg bg-black/40 border border-black/5">
              <div className="mt-0.5">
                {issue.severity === 'high' && <TbAlertTriangle className="w-4 h-4 text-red-400" />}
                {issue.severity === 'medium' && <TbAlertCircle className="w-4 h-4 text-amber-400" />}
                {issue.severity === 'low' && <TbInfoCircle className="w-4 h-4 text-blue-400" />}
              </div>
              <div>
                <p className="text-sm text-zinc-300">{issue.message}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
