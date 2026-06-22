import { useState, useRef, useCallback } from 'react';
import { uploadDataset } from '../services/api';

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
      className={`rounded-2xl border p-5 sm:p-6 transition-colors ${
        isDragging
          ? 'border-indigo-400/50 bg-indigo-950/20'
          : lastUpload
            ? 'border-emerald-500/20 bg-emerald-950/10'
            : 'border-white/8 bg-white/[0.02]'
      }`}
    >
      {!lastUpload ? (
        <div className="text-center space-y-4 py-4">
          <p className="text-4xl">📁</p>
          <div>
            <p className="text-white font-medium">Drop your CSV here</p>
            <p className="text-gray-500 text-sm mt-1">Sales, inventory, payroll — any business spreadsheet</p>
          </div>
          <input type="file" accept=".csv" className="hidden" ref={fileInputRef} onChange={e => processFile(e.target.files[0])} />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="px-5 py-2.5 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-colors"
          >
            {isUploading ? 'Uploading…' : 'Choose file'}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-emerald-400 text-sm font-medium">✓ Data loaded</p>
              <p className="text-white font-semibold mt-1 truncate">{lastUpload.table_name?.replace(/_/g, ' ')}</p>
              <p className="text-gray-500 text-sm mt-0.5">
                {lastUpload.row_count?.toLocaleString()} rows · {lastUpload.columns?.length} columns
              </p>
            </div>
            <input type="file" accept=".csv" className="hidden" ref={fileInputRef} onChange={e => processFile(e.target.files[0])} />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="text-xs text-gray-400 hover:text-white shrink-0 px-3 py-1.5 rounded-lg border border-white/10 hover:border-white/20 transition-colors"
            >
              Replace
            </button>
          </div>

          {businessType && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
              <span className="text-indigo-300 text-xs font-medium">{typeLabel}</span>
              <span className="text-indigo-100 text-sm font-semibold">{businessType}</span>
            </div>
          )}

          <button
            type="button"
            onClick={() => setShowPreview(v => !v)}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            {showPreview ? '▾ Hide preview' : '▸ Preview data'}
          </button>
          {showPreview && <DataPreview upload={lastUpload} />}
        </div>
      )}

      {error && <p className="text-red-400 text-sm mt-3">{error}</p>}
    </section>
  );
}
