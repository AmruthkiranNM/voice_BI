import { useState, useRef, useCallback } from 'react';
import { uploadDataset } from '../services/api';

function DataQuality({ report }) {
  if (!report) return null;
  const { score, issues } = report;
  const color = score >= 85 ? 'text-[#c8ff4d]' : score >= 60 ? 'text-amber-400' : 'text-red-400';

  return (
    <div className="border-l-2 border-white/20 bg-black/20 px-3 py-2 space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400 font-medium">Data quality</span>
        <span className={`text-sm font-data font-semibold ${color}`}>{score}/100</span>
      </div>
      {issues.length > 0 && (
        <ul className="space-y-1">
          {issues.slice(0, 3).map((issue, i) => (
            <li key={i} className="text-xs text-gray-500 leading-snug">• {issue.message}</li>
          ))}
          {issues.length > 3 && (
            <li className="text-xs text-gray-600">+ {issues.length - 3} more</li>
          )}
        </ul>
      )}
    </div>
  );
}

function DataPreview({ upload }) {
  if (!upload?.preview_rows?.length) return null;
  const columns = upload.columns || Object.keys(upload.preview_rows[0]);

  return (
    <div className="overflow-x-auto rounded-lg border border-white/5 bg-black/20 max-h-40 mt-4">
      <table className="w-full text-xs text-left">
        <thead className="text-gray-500 border-b border-white/5">
          <tr>
            {columns.map(col => (
              <th key={col} className="px-3 py-2 font-medium whitespace-nowrap">
                {col.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5 text-gray-400">
          {upload.preview_rows.slice(0, 5).map((row, i) => (
            <tr key={i}>
              {columns.map(col => (
                <td key={col} className="px-3 py-1.5 whitespace-nowrap">{row[col] ?? '—'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DatasetUpload({ onUploadSuccess }) {
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpload, setLastUpload] = useState(null);
  const [showPreview, setShowPreview] = useState(false);
  const fileInputRef = useRef(null);

  const processFile = useCallback(async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Please upload a CSV file.');
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const result = await uploadDataset(file);
      setLastUpload(result);
      setShowPreview(false);
      onUploadSuccess?.(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [onUploadSuccess]);

  const businessType = lastUpload?.domain?.business_type || lastUpload?.domain?.label;
  const typeConfidence = lastUpload?.domain?.confidence ?? 0;
  const typeLabel = typeConfidence >= 0.25 ? 'Detected data type:' : 'Data profile:';

  return (
    <section
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        processFile(e.dataTransfer.files[0]);
      }}
      className={`border p-5 sm:p-6 transition-colors ${
        isDragging
          ? 'border-[#c8ff4d]/50 bg-[#c8ff4d]/[0.04]'
          : lastUpload
            ? 'border-[#c8ff4d]/25 bg-[#c8ff4d]/[0.02]'
            : 'border-white/10 bg-white/[0.02]'
      }`}
    >
      {!lastUpload ? (
        <div className="text-center space-y-4 py-4">
          <svg className="mx-auto" width="32" height="32" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 4v11M7 10l5 5 5-5M4 19h16" stroke="#c8ff4d" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <p className="text-white font-medium">Drop your CSV here</p>
            <p className="text-gray-500 text-sm mt-1">Sales, inventory, payroll — any business spreadsheet</p>
          </div>
          <input type="file" accept=".csv" className="hidden" ref={fileInputRef} onChange={e => processFile(e.target.files[0])} />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="btn-primary px-5 py-2.5 text-sm disabled:opacity-50"
          >
            {isUploading ? 'Uploading…' : 'Choose file'}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[#c8ff4d] text-xs font-data uppercase tracking-wide">Data loaded</p>
              <p className="text-white font-semibold mt-1 truncate">{lastUpload.table_name?.replace(/_/g, ' ')}</p>
              <p className="text-gray-500 text-sm mt-0.5 font-data">
                {lastUpload.row_count?.toLocaleString()} rows · {lastUpload.columns?.length} columns
              </p>
            </div>
            <input type="file" accept=".csv" className="hidden" ref={fileInputRef} onChange={e => processFile(e.target.files[0])} />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="text-xs text-gray-400 hover:text-white shrink-0 px-3 py-1.5 border border-white/10 hover:border-white/25 transition-colors"
            >
              Replace
            </button>
          </div>

          {businessType && (
            <div className="flex items-center gap-2 px-3 py-2 border-l-2 border-[#c8ff4d]/60 bg-black/20">
              <span className="text-gray-400 text-xs font-medium">{typeLabel}</span>
              <span className="text-white text-sm font-semibold">{businessType}</span>
            </div>
          )}

          <DataQuality report={lastUpload.data_quality} />

          <button
            type="button"
            onClick={() => setShowPreview(v => !v)}
            className="text-xs text-gray-400 hover:text-white transition-colors font-data"
          >
            {showPreview ? '− Hide preview' : '+ Preview data'}
          </button>
          {showPreview && <DataPreview upload={lastUpload} />}
        </div>
      )}

      {error && <p className="text-red-400 text-sm mt-3">{error}</p>}
    </section>
  );
}
