import { analyzeResult, formatStatValue } from '../utils/resultAnalytics';

export default function ResultStats({ result }) {
  const analysis = analyzeResult(result);
  if (!analysis?.numericStats?.length) return null;

  const { numericStats, topEntry, rowCount, columnCount } = analysis;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Rows returned" value={rowCount} />
        <StatCard label="Columns" value={columnCount} />
        {topEntry && (
          <>
            <StatCard label="Top result" value={topEntry.label} small />
            <StatCard label={topEntry.valueColumn} value={formatStatValue(topEntry.value)} highlight />
          </>
        )}
      </div>

      {numericStats.length > 0 && (
        <div className="panel-card">
          <h3 className="text-xs font-data uppercase tracking-wide text-gray-500 mb-4">Number breakdown</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {numericStats.map(stat => (
              <div key={stat.column} className="border-l-2 border-[#c8ff4d]/60 bg-black/20 p-4">
                <p className="text-xs text-gray-500 capitalize mb-3">{stat.label}</p>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <MiniStat label="Total" value={formatStatValue(stat.sum)} />
                  <MiniStat label="Average" value={formatStatValue(stat.avg)} />
                  <MiniStat label="Min" value={formatStatValue(stat.min)} />
                  <MiniStat label="Max" value={formatStatValue(stat.max)} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, small, highlight }) {
  return (
    <div className="border-l-2 border-[#c8ff4d]/60 bg-black/20 px-4 py-3">
      <p className="text-[11px] text-gray-500 mb-1">{label}</p>
      <p className={`font-semibold text-white truncate ${small ? 'text-sm' : 'text-lg'} ${highlight ? 'text-[#c8ff4d]' : ''}`}>
        {value}
      </p>
    </div>
  );
}

function MiniStat({ label, value }) {
  return (
    <div>
      <p className="text-[10px] text-gray-600 uppercase tracking-wide">{label}</p>
      <p className="text-white font-medium font-data">{value}</p>
    </div>
  );
}
