import { useMemo, useState } from 'react';
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
  Title, Tooltip, Legend, Filler,
);

const COLORS = [
  'rgba(200, 255, 77, 0.9)',
  'rgba(94, 234, 212, 0.9)',
  'rgba(245, 158, 11, 0.9)',
  'rgba(168, 85, 247, 0.9)',
  'rgba(239, 68, 68, 0.9)',
  'rgba(96, 165, 250, 0.9)',
];

const CHART_TYPES = [
  { id: 'bar', label: 'Bar' },
  { id: 'horizontal', label: 'Horizontal' },
  { id: 'line', label: 'Line' },
  { id: 'doughnut', label: 'Pie' },
];

export default function ChartPanel({ result, intent, fullWidth = false }) {
  const chartData = useMemo(() => {
    if (!result?.columns?.length || !result?.rows?.length) return null;
    return prepareChartData(result, intent);
  }, [result, intent]);

  const [activeType, setActiveType] = useState(null);

  if (!chartData) return null;

  const { labels, datasets, defaultType } = chartData;
  const type = activeType || defaultType;
  const displayRows = Math.min(labels.length, type === 'doughnut' ? 8 : 20);
  const slicedLabels = labels.slice(0, displayRows);
  const slicedDatasets = datasets.map(ds => ({
    ...ds,
    data: ds.data.slice(0, displayRows),
    backgroundColor: type === 'doughnut'
      ? COLORS.slice(0, displayRows)
      : ds.backgroundColor,
  }));

  const data = { labels: slicedLabels, datasets: slicedDatasets };
  const options = buildOptions(type, slicedDatasets.length);

  const heightClass = fullWidth ? 'h-80 lg:h-96' : 'h-72';

  return (
    <div className="space-y-4">
      <div className={`grid gap-6 ${fullWidth ? 'grid-cols-1 xl:grid-cols-2' : 'grid-cols-1'}`}>
        <ChartCard
          title="Primary view"
          type={type}
          data={data}
          options={options}
          heightClass={heightClass}
          chartTypes={CHART_TYPES}
          selectedType={type}
          onTypeChange={setActiveType}
        />

        {fullWidth && chartData.secondary && (
          <ChartCard
            title={chartData.secondary.title}
            type={chartData.secondary.type}
            data={chartData.secondary.data}
            options={buildOptions(chartData.secondary.type, 1)}
            heightClass={heightClass}
            readOnly
          />
        )}
      </div>

      {labels.length > displayRows && (
        <p className="text-xs text-gray-600 text-center">
          Showing top {displayRows} of {labels.length} results in chart
        </p>
      )}
    </div>
  );
}

function ChartCard({ title, type, data, options, heightClass, chartTypes, selectedType, onTypeChange, readOnly }) {
  return (
    <div className="panel-card flex flex-col">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <h3 className="text-xs font-data uppercase tracking-wide text-gray-500">{title}</h3>
        {!readOnly && chartTypes && (
          <div className="flex gap-1">
            {chartTypes.map(ct => (
              <button
                key={ct.id}
                type="button"
                onClick={() => onTypeChange(ct.id)}
                className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                  selectedType === ct.id
                    ? 'bg-[#c8ff4d] text-[#0a0a08]'
                    : 'text-gray-500 hover:text-white bg-white/5'
                }`}
              >
                {ct.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className={`relative w-full ${heightClass} min-h-[240px]`}>
        {type === 'bar' && <Bar data={data} options={options} />}
        {type === 'horizontal' && <Bar data={data} options={{ ...options, indexAxis: 'y' }} />}
        {type === 'line' && <Line data={data} options={options} />}
        {type === 'doughnut' && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-full max-w-sm aspect-square">
              <Doughnut data={data} options={options} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function prepareChartData(result, intent) {
  const { columns, rows } = result;
  const labelCol = columns.find(c => rows.some(r => isNaN(Number(r[c])))) || columns[0];
  const valCols = columns.filter(c => c !== labelCol && rows.some(r => !isNaN(Number(r[c]))));
  if (!valCols.length) return null;

  const sorted = [...rows].sort(
    (a, b) => Number(b[valCols[0]]) - Number(a[valCols[0]]),
  );
  const labels = sorted.map(r => String(r[labelCol]));
  const isTime = labels.some(l =>
    /^\d{4}[-/]|^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/i.test(l),
  );

  let defaultType = 'bar';
  if (isTime || intent === 'trend') defaultType = 'line';
  else if (rows.length <= 6 && valCols.length === 1) defaultType = 'doughnut';
  else if (rows.length > 8) defaultType = 'horizontal';

  const datasets = valCols.map((col, i) => ({
    label: col.replace(/_/g, ' '),
    data: sorted.map(r => Number(r[col]) || 0),
    backgroundColor: COLORS[i % COLORS.length],
    borderColor: COLORS[i % COLORS.length],
    borderWidth: defaultType === 'line' ? 2 : defaultType === 'doughnut' ? 2 : 0,
    borderRadius: 4,
    fill: defaultType === 'line',
    tension: 0.35,
    pointRadius: 3,
  }));

  let secondary = null;
  if (valCols.length >= 2) {
    secondary = {
      title: 'Metric comparison',
      type: 'bar',
      data: {
        labels: valCols.map(c => c.replace(/_/g, ' ')),
        datasets: [{
          label: 'Total',
          data: valCols.map(col =>
            rows.reduce((sum, r) => sum + (Number(r[col]) || 0), 0),
          ),
          backgroundColor: COLORS,
          borderRadius: 4,
        }],
      },
    };
  } else if (rows.length > 3) {
    const values = sorted.map(r => Number(r[valCols[0]]) || 0);
    const total = values.reduce((a, b) => a + b, 0);
    const avg = total / values.length;
    secondary = {
      title: 'Distribution',
      type: 'bar',
      data: {
        labels: ['Total', 'Average', 'Highest', 'Lowest'],
        datasets: [{
          label: valCols[0].replace(/_/g, ' '),
          data: [total, avg, Math.max(...values), Math.min(...values)],
          backgroundColor: COLORS.slice(0, 4),
          borderRadius: 4,
        }],
      },
    };
  }

  return { labels, datasets, defaultType, secondary };
}

function buildOptions(type, datasetCount) {
  const isHorizontal = type === 'horizontal';
  const isDoughnut = type === 'doughnut';

  return {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: isHorizontal ? 'y' : 'x',
    plugins: {
      legend: {
        display: datasetCount > 1 || isDoughnut,
        position: isDoughnut ? 'right' : 'top',
        labels: { color: '#9CA3AF', font: { size: 11 }, usePointStyle: true, boxWidth: 8 },
      },
      tooltip: {
        backgroundColor: 'rgba(18, 18, 16, 0.95)',
        titleColor: '#F2F2EE',
        bodyColor: '#D1D5DB',
        borderColor: 'rgba(255,255,255,0.12)',
        borderWidth: 1,
        padding: 10,
      },
    },
    ...(!isDoughnut && {
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
          ticks: { color: '#9CA3AF', font: { size: 10 }, maxRotation: isHorizontal ? 0 : 45 },
          border: { display: false },
          ...(isHorizontal && { beginAtZero: true }),
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
          ticks: {
            color: '#9CA3AF',
            font: { size: 10 },
            ...(isHorizontal
              ? {}
              : {
                  callback: v =>
                    v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : v,
                }),
          },
          border: { display: false },
          ...(!isHorizontal && { beginAtZero: true }),
        },
      },
    }),
  };
}
