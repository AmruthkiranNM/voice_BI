import { TbFileSpreadsheet } from 'react-icons/tb';

const TILE_ACCENTS = ['#3E7A4D', '#B8965A', '#9C4A2A', '#3E7A4D'];

function summarize(issues, type) {
  return issues.filter(i => i.type === type);
}

/**
 * Full-page data-quality report — the same score/issues object the compact
 * DataQuality card uses (computed in backend/services/data_quality.py from
 * the raw dataframe, no LLM involved), presented as a dedicated workspace
 * view instead of a small inline card.
 */
export default function DataQualityPage({ quality, tableName, onContinue }) {
  if (!quality) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20 text-zinc-500 text-sm">
        Upload a dataset first to see its quality report.
      </div>
    );
  }

  const { score, issue_count, issues = [] } = quality;

  const missing = summarize(issues, 'missing_values');
  const duplicates = summarize(issues, 'duplicate_rows')[0];
  const typeMismatches = summarize(issues, 'inconsistent_type');
  const constants = summarize(issues, 'constant_column');

  const worstMissingPct = missing.length ? Math.max(...missing.map(i => i.pct)) : 0;

  const tiles = [
    { label: 'Missing values', value: missing.length ? `${worstMissingPct}%` : '0%' },
    { label: 'Duplicates', value: duplicates ? `${duplicates.count} rows` : '0 rows' },
    { label: 'Type mismatches', value: `${typeMismatches.length} cols` },
    { label: 'Constant cols', value: `${constants.length}` },
  ];

  return (
    <div className="max-w-4xl mx-auto animate-in">
      <div className="pb-6 border-b" style={{ borderColor: 'var(--color-border)' }}>
        <p className="bi-header-eyebrow flex items-center gap-1.5">
          <TbFileSpreadsheet className="w-3 h-3" />
          Data Quality {tableName ? `· ${tableName.replace(/_/g, ' ')}` : ''}
        </p>
        <h1 className="bi-header-title" style={{ fontSize: 'clamp(1.5rem, 3vw, 2rem)' }}>
          Your data is {score}% clean
        </h1>
        <p className="text-sm text-zinc-500 mt-2 max-w-xl">
          Computed directly from the file — no model involved.
          {issue_count === 0
            ? ' No issues found.'
            : ` ${issue_count} thing${issue_count > 1 ? 's' : ''} worth a look before you analyze.`}
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 py-7">
        {tiles.map((t, i) => (
          <div
            key={t.label}
            className="surface-card p-4"
            style={{ borderTop: `3px solid ${TILE_ACCENTS[i]}`, borderRadius: '10px' }}
          >
            <p className="text-[10px] uppercase tracking-wide font-semibold text-zinc-500 mb-2">{t.label}</p>
            <p className="font-serif text-xl" style={{ fontFamily: "'Source Serif 4', Georgia, serif" }}>{t.value}</p>
          </div>
        ))}
      </div>

      {issues.length > 0 && (
        <div className="space-y-4">
          <p className="bi-header-eyebrow">Findings</p>
          {issues.map((issue, i) => (
            <div key={i} className="pl-3.5" style={{ borderLeft: `3px solid ${TILE_ACCENTS[i % TILE_ACCENTS.length]}` }}>
              <p className="text-[15px] font-semibold" style={{ fontFamily: "'Source Serif 4', Georgia, serif" }}>
                {issue.message}
              </p>
              {issue.column && (
                <p className="text-xs text-zinc-500 mt-0.5">Column: {issue.column.replace(/_/g, ' ')}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {onContinue && (
        <button onClick={onContinue} className="btn-primary mt-8 px-6 py-2.5 text-sm rounded-lg">
          Continue to analysis →
        </button>
      )}
    </div>
  );
}
