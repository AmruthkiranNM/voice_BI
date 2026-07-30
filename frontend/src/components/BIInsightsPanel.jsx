import { useMemo, useState, useCallback, useRef } from 'react';
import {
  TbTrophy, TbAlertTriangle, TbTrendingUp, TbCircleFilled,
  TbBulb, TbSearch, TbLink, TbChartBar, TbBrain, TbChevronUp, TbChevronDown,
} from 'react-icons/tb';
import { analyzeResult, formatStatValue, buildCallouts, periodComparison } from '../utils/resultAnalytics';
import { BI_COLORS } from '../utils/biPalette';

const INSIGHT_ICONS = {
  top: TbTrophy,
  low: TbAlertTriangle,
  trend: TbTrendingUp,
  risk: TbCircleFilled,
  opportunity: TbBulb,
  pattern: TbSearch,
  correlation: TbLink,
  neutral: TbChartBar,
};

export default function BIInsightsPanel({ result, intent = '', query = '' }) {
  const analysis = useMemo(() => analyzeResult(result, intent, query), [result, intent, query]);
  const callouts = useMemo(() => buildCallouts(result), [result]);
  const trend = useMemo(() => periodComparison(result), [result]);
  const [expanded, setExpanded] = useState(true);

  if (!analysis) return null;

  const { numericStats, topEntry, rowCount } = analysis;
  const primaryStat = numericStats?.[0];

  // Contribution % for top items
  const rows = result?.rows ?? [];
  const columns = result?.columns ?? [];
  const numericCol = numericStats?.[0]?.column;
  const labelCol = analysis.labelCol;

  const topItems = useMemo(() => {
    if (!numericCol || !labelCol || !rows.length) return [];
    const total = rows.reduce((s, r) => s + (Number(r[numericCol]) || 0), 0);
    return [...rows]
      .sort((a, b) => Number(b[numericCol]) - Number(a[numericCol]))
      .slice(0, 5)
      .map((r, i) => ({
        label: String(r[labelCol] ?? '—'),
        value: Number(r[numericCol]) || 0,
        pct: total ? ((Number(r[numericCol]) || 0) / total) * 100 : 0,
        rank: i + 1,
        color: BI_COLORS[i % BI_COLORS.length],
      }));
  }, [rows, numericCol, labelCol]);

  const bottomItem = useMemo(() => {
    if (!numericCol || !labelCol || !rows.length) return null;
    const sorted = [...rows].sort((a, b) => Number(a[numericCol]) - Number(b[numericCol]));
    const r = sorted[0];
    const total = rows.reduce((s, row) => s + (Number(row[numericCol]) || 0), 0);
    return {
      label: String(r?.[labelCol] ?? '—'),
      value: Number(r?.[numericCol]) || 0,
      pct: total ? ((Number(r?.[numericCol]) || 0) / total) * 100 : 0,
    };
  }, [rows, numericCol, labelCol]);

  const cards = [];

  // Top Performer
  if (topEntry) {
    cards.push({
      type: 'top',
      title: 'Top Performer',
      icon: INSIGHT_ICONS.top,
      label: topEntry.label,
      value: formatStatValue(topEntry.value),
      sub: topEntry.valueColumn,
      accent: '#9C4A2A',
      badge: 'Rank #1',
    });
  }

  // Lowest Performer
  if (bottomItem && bottomItem.label !== topEntry?.label) {
    cards.push({
      type: 'low',
      title: 'Lowest Performer',
      icon: INSIGHT_ICONS.low,
      label: bottomItem.label,
      value: formatStatValue(bottomItem.value),
      sub: `${bottomItem.pct.toFixed(1)}% of total`,
      accent: '#9C4A2A',
      badge: 'Needs Attention',
    });
  }

  // Period trend
  if (trend && trend.pct != null) {
    cards.push({
      type: trend.direction === 'up' ? 'trend' : 'risk',
      title: trend.direction === 'up' ? 'Growth Signal' : 'Decline Alert',
      icon: trend.direction === 'up' ? INSIGHT_ICONS.trend : INSIGHT_ICONS.risk,
      label: trend.column,
      value: `${trend.direction === 'up' ? '+' : ''}${trend.pct.toFixed(1)}%`,
      sub: `${formatStatValue(trend.previous)} → ${formatStatValue(trend.current)}`,
      accent: trend.direction === 'up' ? '#3E7A4D' : '#9C4A2A',
      badge: trend.direction === 'up' ? 'Positive' : 'Negative',
    });
  }

  // Summary stat
  if (primaryStat) {
    cards.push({
      type: 'neutral',
      title: 'Total',
      icon: INSIGHT_ICONS.neutral,
      label: primaryStat.label,
      value: formatStatValue(primaryStat.sum),
      sub: `Avg: ${formatStatValue(primaryStat.avg)} · Max: ${formatStatValue(primaryStat.max)}`,
      accent: '#B5613C',
      badge: `${rowCount} records`,
    });
  }

  // Pattern callouts
  for (const c of callouts.slice(0, 2)) {
    cards.push({
      type: c.type === 'positive' ? 'opportunity' : c.type === 'negative' ? 'risk' : 'pattern',
      title: c.type === 'positive' ? 'Opportunity' : c.type === 'negative' ? 'Risk Indicator' : 'Pattern',
      icon: c.type === 'positive' ? INSIGHT_ICONS.opportunity : c.type === 'negative' ? INSIGHT_ICONS.risk : INSIGHT_ICONS.pattern,
      label: '',
      value: '',
      sub: c.text,
      accent: c.type === 'positive' ? '#3E7A4D' : c.type === 'negative' ? '#9C4A2A' : '#B8965A',
      badge: null,
    });
  }

  if (!cards.length) return null;

  return (
    <div className="bi-insights-panel">
      <div className="bi-insights-header" onClick={() => setExpanded(v => !v)}>
        <h3 className="bi-insights-title">
          <TbBrain className="w-4 h-4" /> Business Insights
        </h3>
        <button className="bi-insights-toggle">
          {expanded ? <TbChevronUp className="w-4 h-4" /> : <TbChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {expanded && (
        <div className="bi-insights-grid">
          {cards.map((card, i) => (
            <InsightCard key={i} card={card} />
          ))}
        </div>
      )}

      {/* Top contributors bar chart */}
      {expanded && topItems.length > 1 && (
        <div className="bi-contribution-bars">
          <p className="bi-contrib-title">Top Contributors — {numericCol?.replace(/_/g, ' ')}</p>
          {topItems.map(item => (
            <div key={item.label} className="bi-contrib-row">
              <div className="bi-contrib-label" title={item.label}>
                <span className="bi-contrib-rank" style={{ color: item.color }}>#{item.rank}</span>
                {item.label}
              </div>
              <div className="bi-contrib-bar-wrap">
                <div
                  className="bi-contrib-bar"
                  style={{ width: `${Math.min(item.pct, 100)}%`, background: item.color }}
                />
              </div>
              <div className="bi-contrib-meta">
                <span className="bi-contrib-val">{formatStatValue(item.value)}</span>
                <span className="bi-contrib-pct">{item.pct.toFixed(1)}%</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function InsightCard({ card }) {
  const Icon = card.icon;
  return (
    <div className="bi-insight-card" style={{ '--insight-accent': card.accent }}>
      <div className="bi-insight-card-header">
        <span className="bi-insight-icon"><Icon className="w-4 h-4" style={{ color: card.accent }} /></span>
        <span className="bi-insight-title">{card.title}</span>
        {card.badge && (
          <span className="bi-insight-badge" style={{ borderColor: card.accent, color: card.accent }}>
            {card.badge}
          </span>
        )}
      </div>
      {card.label && <p className="bi-insight-label">{card.label}</p>}
      {card.value && <p className="bi-insight-value" style={{ color: card.accent }}>{card.value}</p>}
      {card.sub && <p className="bi-insight-sub">{card.sub}</p>}
    </div>
  );
}
