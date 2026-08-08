import { TbSearch, TbArrowDown, TbSparkles } from 'react-icons/tb';
import RichText from './RichText';

/**
 * Renders the result of an autonomous multi-hop drill-down (POST /api/investigate):
 * the chain of follow-up questions the system asked itself, each with what it
 * found, ending in a synthesized root-cause narrative. This is what makes the
 * system reason instead of just answer — every hop after the first was decided
 * by the model, not the user.
 */
export default function InvestigationTrail({ investigation, isLoading }) {
  if (isLoading) {
    return (
      <div className="panel-card animate-in">
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <TbSearch className="w-4 h-4 animate-pulse text-[#9C4A2A]" />
          Investigating — asking itself follow-up questions...
        </div>
      </div>
    );
  }

  if (!investigation) return null;

  const { chain = [], narrative, hops } = investigation;

  if (hops === 0) {
    return (
      <div className="panel-card animate-in">
        <p className="text-sm text-zinc-500">
          Nothing further to dig into — this result looks self-explanatory.
        </p>
      </div>
    );
  }

  return (
    <div className="panel-card animate-in">
      <div className="flex items-center gap-2 mb-5">
        <TbSearch className="w-4 h-4 text-[#9C4A2A]" />
        <h3 className="text-xs font-data uppercase tracking-wide text-zinc-500">
          Investigation trail — {hops} follow-up{hops > 1 ? 's' : ''} the system asked itself
        </h3>
      </div>

      <div className="space-y-0">
        {chain.map((step, i) => (
          <div key={i}>
            <div className="flex items-start gap-3 pl-3.5" style={{ borderLeft: '3px solid #9C4A2A' }}>
              <span className="text-xs font-data font-semibold text-[#9C4A2A] mt-0.5 shrink-0">
                {i === 0 ? 'Q' : `+${i}`}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-zinc-200">{step.question}</p>
                <FindingTable finding={step.finding} />
              </div>
            </div>
            {i < chain.length - 1 && (
              <div className="flex items-center justify-center py-1.5">
                <TbArrowDown className="w-3.5 h-3.5 text-zinc-600" />
              </div>
            )}
          </div>
        ))}
      </div>

      {narrative && (
        <div className="mt-5 pt-5 border-t border-black/10">
          <div className="flex items-center gap-2 mb-2">
            <TbSparkles className="w-3.5 h-3.5 text-[#9C4A2A]" />
            <span className="text-xs font-data uppercase tracking-wide text-zinc-500">Root cause</span>
          </div>
          <RichText text={narrative} className="text-sm sm:text-base text-ink" />
        </div>
      )}
    </div>
  );
}

/** Compact table for one hop's finding — up to 5 rows, numbers formatted, instead of a flattened key:value text dump. */
function FindingTable({ finding }) {
  const { columns = [], rows = [], row_count = 0, truncated = false } = finding || {};

  if (!rows.length) {
    return <p className="text-xs text-zinc-500 mt-1">No matching rows.</p>;
  }

  return (
    <div className="mt-2 overflow-x-auto rounded-lg border border-black/10">
      <table className="w-full text-xs text-left whitespace-nowrap">
        <thead className="bg-black/[0.02] text-zinc-500 border-b border-black/10">
          <tr>
            {columns.map(col => (
              <th key={col} className="px-3 py-1.5 font-medium uppercase tracking-wide text-[10px]">
                {col.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-black/5 text-zinc-300">
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map(col => (
                <td key={col} className="px-3 py-1.5">
                  {formatCell(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {truncated && (
        <p className="text-[10px] text-zinc-600 px-3 py-1.5 bg-black/[0.02] border-t border-black/10">
          +{(row_count - rows.length).toLocaleString()} more rows
        </p>
      )}
    </div>
  );
}

function formatCell(value) {
  if (value == null || value === '') return <span className="text-zinc-600">—</span>;
  const n = Number(value);
  if (!Number.isNaN(n) && typeof value !== 'boolean' && String(value).trim() !== '') {
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
}
