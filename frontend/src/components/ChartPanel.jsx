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
  'rgba(99, 102, 241, 0.9)',
  'rgba(34, 197, 94, 0.9)',
  'rgba(245, 158, 11, 0.9)',
  'rgba(6, 182, 212, 0.9)',
  'rgba(239, 68, 68, 0.9)',
  'rgba(168, 85, 247, 0.9)',
];

export default function ChartPanel({ result, intent }) {
  const config = useMemo(() => {
    if (!result?.columns?.length || !result?.rows?.length) return null;
    return buildChart(result, intent);
  }, [result, intent]);

  if (!config) return null;
  const { type, data, options } = config;

  return (
    <div className="panel-card w-full h-[420px]">
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-pink-500/10 flex items-center justify-center text-pink-400">📈</div>
          <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider">Visualization</h3>
        </div>
        <span className="px-3 py-1 rounded-md bg-gray-800 text-gray-400 border border-gray-700 text-xs font-bold uppercase">
          {type} CHART
        </span>
      </div>

      <div className="relative w-full flex-1 min-h-0">
        {type === 'bar' && <Bar data={data} options={options} />}
        {type === 'line' && <Line data={data} options={options} />}
        {type === 'doughnut' && (
          <div className="absolute inset-0 flex items-center justify-center">
             <div className="w-full max-w-[300px] aspect-square">
                <Doughnut data={data} options={options} />
             </div>
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
    label: col.replace(/_/g, ' ').toUpperCase(),
    data: rows.map(r => Number(r[col]) || 0),
    backgroundColor: type === 'doughnut' ? COLORS.slice(0, rows.length) : COLORS[i],
    borderColor: type === 'doughnut' ? '#111827' : COLORS[i],
    borderWidth: type === 'line' ? 3 : type === 'doughnut' ? 3 : 0,
    borderRadius: type === 'bar' ? 4 : 0,
    fill: type === 'line' ? { target: 'origin', above: COLORS[i].replace('0.9', '0.1') } : false,
    tension: 0.4,
    pointRadius: 4,
    pointBackgroundColor: COLORS[i],
    pointBorderColor: '#111827',
    pointBorderWidth: 2,
  }));

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    layout: { padding: { top: 10, bottom: 10 } },
    plugins: {
      legend: {
        display: valCols.length > 1 || type === 'doughnut',
        position: type === 'doughnut' ? 'right' : 'top',
        labels: { color: '#9CA3AF', font: { size: 11, weight: 'bold' }, padding: 20, usePointStyle: true, boxWidth: 8 },
      },
      tooltip: {
        backgroundColor: 'rgba(17, 24, 39, 0.9)',
        titleColor: '#F3F4F6',
        bodyColor: '#D1D5DB',
        borderColor: '#374151',
        borderWidth: 1,
        padding: 12,
        cornerRadius: 8,
        titleFont: { size: 13, weight: 'bold' },
        bodyFont: { size: 12 },
        displayColors: true,
        boxPadding: 6,
      },
    },
    ...(type !== 'doughnut' && {
      scales: {
        x: {
          grid: { color: 'rgba(31,41,55,0.6)', drawBorder: false },
          ticks: { color: '#9CA3AF', font: { size: 11 }, maxRotation: 45 },
          border: { display: false },
        },
        y: {
          grid: { color: 'rgba(31,41,55,0.6)', drawBorder: false },
          ticks: {
            color: '#9CA3AF', font: { size: 11 },
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
