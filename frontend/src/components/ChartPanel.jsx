/**
 * ChartPanel — Auto-generated Chart.js visualization
 */
import { useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale,
  BarElement, LineElement, PointElement, ArcElement,
  Title, Tooltip, Legend, Filler,
} from 'chart.js';
import { Bar, Line, Doughnut } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale, LinearScale,
  BarElement, LineElement, PointElement, ArcElement,
  Title, Tooltip, Legend, Filler
);

const COLORS = [
  'rgba(99, 102, 241, 0.85)',
  'rgba(34, 197, 94, 0.85)',
  'rgba(245, 158, 11, 0.85)',
  'rgba(6, 182, 212, 0.85)',
  'rgba(239, 68, 68, 0.85)',
  'rgba(168, 85, 247, 0.85)',
];

export default function ChartPanel({ result, intent }) {
  const config = useMemo(() => {
    if (!result?.columns?.length || !result?.rows?.length) return null;
    return buildChart(result, intent);
  }, [result, intent]);

  if (!config) return null;

  const { type, data, options } = config;

  return (
    <div className="bg-card border border-border rounded-2xl p-6 fade-up-3
                    hover:border-border-hover transition-colors duration-200">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <span className="text-lg">📈</span>
          <h3 className="text-sm font-bold text-text-primary uppercase tracking-wide">
            Visualization
          </h3>
        </div>
        <span className="text-[11px] text-text-muted capitalize font-medium">{type} chart</span>
      </div>

      <div className="h-[280px]">
        {type === 'bar' && <Bar data={data} options={options} />}
        {type === 'line' && <Line data={data} options={options} />}
        {type === 'doughnut' && (
          <div className="max-w-[260px] mx-auto h-full">
            <Doughnut data={data} options={options} />
          </div>
        )}
      </div>
    </div>
  );
}

function buildChart(result, intent) {
  const { columns, rows } = result;

  const labelCol = columns.find(c => rows.some(r => isNaN(Number(r[c])))) || columns[0];
  const valCols = columns.filter(c => c !== labelCol && rows.some(r => !isNaN(Number(r[c]))));
  if (!valCols.length) return null;

  const labels = rows.map(r => String(r[labelCol]));
  const isTime = labels.some(l => /^\d{4}[-/]|^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/i.test(l));

  let type = isTime || intent === 'trend' ? 'line' : rows.length <= 6 && valCols.length === 1 ? 'doughnut' : 'bar';

  const datasets = valCols.map((col, i) => ({
    label: col.replace(/_/g, ' '),
    data: rows.map(r => Number(r[col]) || 0),
    backgroundColor: type === 'doughnut' ? COLORS.slice(0, rows.length) : COLORS[i],
    borderColor: type === 'doughnut' ? '#111827' : COLORS[i],
    borderWidth: type === 'line' ? 2.5 : type === 'doughnut' ? 2 : 0,
    borderRadius: type === 'bar' ? 6 : 0,
    fill: type === 'line',
    tension: 0.4,
    pointRadius: 4,
    pointBackgroundColor: COLORS[i],
  }));

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: valCols.length > 1 || type === 'doughnut',
        position: type === 'doughnut' ? 'right' : 'top',
        labels: { color: '#9CA3AF', font: { size: 11, family: 'Inter' }, padding: 16, usePointStyle: true },
      },
      tooltip: {
        backgroundColor: '#1F2937',
        titleColor: '#E5E7EB',
        bodyColor: '#9CA3AF',
        borderColor: '#374151',
        borderWidth: 1,
        padding: 12,
        cornerRadius: 8,
      },
    },
    ...(type !== 'doughnut' && {
      scales: {
        x: {
          grid: { color: 'rgba(31,41,55,0.5)', drawBorder: false },
          ticks: { color: '#6B7280', font: { size: 10 }, maxRotation: 45 },
          border: { display: false },
        },
        y: {
          grid: { color: 'rgba(31,41,55,0.5)', drawBorder: false },
          ticks: {
            color: '#6B7280', font: { size: 10 },
            callback: v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(1)}K` : v,
          },
          border: { display: false },
          beginAtZero: true,
        },
      },
    }),
  };

  return { type, data: { labels, datasets }, options };
}
