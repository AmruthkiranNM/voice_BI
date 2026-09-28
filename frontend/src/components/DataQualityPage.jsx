import { useState } from 'react';
import { TbCircleCheck, TbAlertTriangle, TbAlertOctagon, TbBulb, TbChevronDown, TbChevronRight } from 'react-icons/tb';
import TablePreviewCard from './TablePreviewCard';
import TabbedTables from './TabbedTables';
import { useTablePreviews } from '../hooks/useTablePreviews';

const VERDICT_STYLE = {
  ready:     { color: '#3E7A4D', bg: 'rgba(62,122,77,0.08)',  Icon: TbCircleCheck },
  care:      { color: '#B8965A', bg: 'rgba(184,150,90,0.10)', Icon: TbAlertTriangle },
  attention: { color: '#9C4A2A', bg: 'rgba(156,74,42,0.08)',  Icon: TbAlertOctagon },
};

const SEVERITY_COLOR = { high: '#9C4A2A', medium: '#B8965A', low: '#8F8474' };

/** One finding: what's wrong, what it means for answers, and what to do. */
function FindingCard({ issue }) {
  return (
    <div className="surface-card p-4" style={{ borderLeft: `3px solid ${SEVERITY_COLOR[issue.severity]}`, borderRadius: '10px' }}>
      <p className="text-[15px] font-semibold text-zinc-100" style={{ fontFamily: "'Source Serif 4', Georgia, serif" }}>
        {issue.title || issue.message}
      </p>
      {issue.impact && <p className="text-sm text-zinc-400 mt-1.5">{issue.impact}</p>}
      {issue.examples?.length > 0 && issue.type === 'inconsistent_type' && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {issue.examples.map(ex => (
            <code key={ex} className="text-xs px-1.5 py-0.5 rounded bg-black/5 text-zinc-300">{ex}</code>
          ))}
        </div>
      )}
      {issue.tip && (
        <p className="text-xs text-zinc-500 mt-2 flex gap-1.5">
          <TbBulb className="w-3.5 h-3.5 shrink-0 mt-px text-[#B8965A]" />
          <span>{issue.tip}</span>
        </p>
      )}
    </div>
  );
}

/** Per-column completeness, least complete first, so gaps are visible at a glance. */
function ColumnCompleteness({ columns }) {
  if (!columns?.length) return null;
  const incomplete = [...columns].filter(c => c.filled_pct < 100).sort((a, b) => a.filled_pct - b.filled_pct);
  const completeCount = columns.length - incomplete.length;
  return (
    <div className="mb-8">
      <p className="bi-header-eyebrow mb-3">
        {incomplete.length === 0
          ? `Column completeness — all ${columns.length} columns are fully filled in`
          : `Columns with gaps — the other ${completeCount} are fully filled in`}
      </p>
      {incomplete.length > 0 && (
        <div className="grid sm:grid-cols-2 gap-x-8 gap-y-2">
          {incomplete.map(c => {
            const color = c.filled_pct >= 95 ? '#3E7A4D' : c.filled_pct >= 60 ? '#B8965A' : '#9C4A2A';
            return (
              <div key={c.name} className="flex items-center gap-3 text-xs">
                <span className="w-32 truncate text-zinc-400" title={c.name}>{c.name.replace(/_/g, ' ')}</span>
                <div className="flex-1 h-1.5 rounded-full bg-black/10 overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${c.filled_pct}%`, background: color }} />
                </div>
                <span className="w-12 text-right tabular-nums text-zinc-500">{c.filled_pct}%</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** One table's quality verdict + findings + completeness + sample rows, shown inside its tab panel. */
function TableQualityPanel({ preview }) {
  const [showInfo, setShowInfo] = useState(false);
  if (!preview) return <p className="text-sm text-zinc-500">Computing data quality…</p>;

  const { score, issues = [], verdict, columns } = preview.data_quality || {};
  // Older reports (no groups) are treated as "could affect answers".
  const affecting = issues.filter(i => (i.group || 'answers') === 'answers');
  const info = issues.filter(i => i.group === 'info');
  const v = verdict || { level: issues.length ? 'care' : 'ready', label: `${score}% clean`, summary: '' };
  const style = VERDICT_STYLE[v.level] || VERDICT_STYLE.care;
  const { Icon } = style;

  return (
    <div>
      <div className="flex items-start gap-3 p-4 rounded-xl mb-6" style={{ background: style.bg }}>
        <Icon className="w-7 h-7 shrink-0" style={{ color: style.color }} />
        <div className="flex-1 min-w-0">
          <h2 className="bi-header-title" style={{ fontSize: 'clamp(1.2rem, 2.4vw, 1.5rem)', color: style.color }}>
            {v.label}
          </h2>
          {v.summary && <p className="text-sm text-zinc-400 mt-1">{v.summary}</p>}
        </div>
        {score != null && (
          <div className="text-right shrink-0">
            <p className="text-[10px] uppercase tracking-wide font-semibold text-zinc-500">Quality score</p>
            <p className="font-serif text-xl text-zinc-200" style={{ fontFamily: "'Source Serif 4', Georgia, serif" }}>{score}/100</p>
          </div>
        )}
      </div>

      {affecting.length > 0 && (
        <div className="space-y-3 mb-6">
          <p className="bi-header-eyebrow">Could affect your answers</p>
          {affecting.map((issue, i) => <FindingCard key={i} issue={issue} />)}
        </div>
      )}

      {info.length > 0 && (
        <div className="mb-6">
          <button
            type="button"
            onClick={() => setShowInfo(s => !s)}
            className="bi-header-eyebrow flex items-center gap-1 hover:text-zinc-300 transition-colors"
          >
            {showInfo ? <TbChevronDown className="w-3.5 h-3.5" /> : <TbChevronRight className="w-3.5 h-3.5" />}
            Good to know ({info.length}) — won't change your answers
          </button>
          {showInfo && (
            <div className="space-y-3 mt-3">
              {info.map((issue, i) => <FindingCard key={i} issue={issue} />)}
            </div>
          )}
        </div>
      )}

      <ColumnCompleteness columns={columns} />

      <p className="bi-header-eyebrow mb-3">Table preview</p>
      <TablePreviewCard preview={preview} />
    </div>
  );
}

/**
 * Data-quality report for every table in the active source, switchable via
 * tabs — score/tiles/findings plus a sample-rows preview per table,
 * computed live (backend/services/data_quality.py, no LLM involved) via
 * GET /api/datasets/{table}/preview.
 */
export default function DataQualityPage({ tableNames = [], onContinue }) {
  const { previews } = useTablePreviews(tableNames);

  if (!tableNames.length) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20 text-zinc-500 text-sm">
        Upload a dataset first to see its quality report.
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto animate-in">
      <div className="pb-6 border-b mb-8" style={{ borderColor: 'var(--color-border)' }}>
        <p className="bi-header-eyebrow">Data Quality</p>
        <h1 className="bi-header-title" style={{ fontSize: 'clamp(1.5rem, 3vw, 2rem)' }}>
          {tableNames.length > 1 ? `${tableNames.length} tables in this source` : tableNames[0].replace(/_/g, ' ')}
        </h1>
        <p className="text-sm text-zinc-500 mt-2 max-w-xl">
          Computed directly from each table — no model involved.
        </p>
      </div>

      <TabbedTables
        tableNames={tableNames}
        previews={previews}
        renderTable={(name, preview) => <TableQualityPanel key={name} preview={preview} />}
      />

      {onContinue && (
        <button onClick={onContinue} className="btn-primary mt-8 px-6 py-2.5 text-sm rounded-lg">
          Continue to analysis →
        </button>
      )}
    </div>
  );
}
