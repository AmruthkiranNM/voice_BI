import { useState, useRef, useCallback } from 'react';
import { uploadDataset } from '../services/api';
import { TbCloudUpload, TbFileSpreadsheet, TbCheck, TbAlertCircle } from 'react-icons/tb';

function DataQuality({ report }) {
  if (!report) return null;
  const { score, issues } = report;
  const colorClass = score >= 85 ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20' 
                   : score >= 60 ? 'text-amber-400 bg-amber-400/10 border-amber-400/20' 
                   : 'text-red-400 bg-red-400/10 border-red-400/20';

  return (
    <div className="mt-4 p-4 rounded-lg bg-white/[0.02] border border-white/5 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-400">Data Quality Score</span>
        <div className={`px-2.5 py-1 rounded-full border text-xs font-bold ${colorClass}`}>
          {score}/100
        </div>
      </div>
      {issues.length > 0 && (
        <ul className="space-y-1.5">
          {issues.slice(0, 3).map((issue, i) => (
            <li key={i} className="text-xs text-zinc-500 flex items-start gap-2">
              <TbAlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-500/70" />
              <span className="leading-snug">{issue.message}</span>
            </li>
          ))}
          {issues.length > 3 && (
            <li className="text-xs text-zinc-600 pl-5 pt-1 font-medium">
              +{issues.length - 3} more issues detected
            </li>
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
    <div className="mt-4 rounded-lg border border-white/10 bg-black/40 overflow-hidden">
      <div className="overflow-x-auto max-h-48 scrollbar-thin">
        <table className="w-full text-xs text-left whitespace-nowrap">
          <thead className="sticky top-0 bg-[#18181b] text-zinc-400 border-b border-white/10 z-10">
            <tr>
              {columns.map(col => (
                <th key={col} className="px-4 py-2.5 font-medium uppercase tracking-wider text-[10px]">
                  {col.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 text-zinc-300">
            {upload.preview_rows.slice(0, 5).map((row, i) => (
              <tr key={i} className="hover:bg-white/5 transition-colors">
                {columns.map(col => (
                  <td key={col} className="px-4 py-2 truncate max-w-[200px]">
                    {row[col] ?? <span className="text-zinc-600">—</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
      setShowPreview(true);
      onUploadSuccess?.(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [onUploadSuccess]);

  const businessType = lastUpload?.domain?.business_type || lastUpload?.domain?.label;

  return (
    <section className="w-full">
      {!lastUpload ? (
        <div
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            processFile(e.dataTransfer.files[0]);
          }}
          className={`
            relative group flex flex-col items-center justify-center w-full h-64 sm:h-72
            rounded-2xl border-2 border-dashed transition-all duration-300 ease-in-out
            ${isDragging 
              ? 'border-blue-500 bg-blue-500/10' 
              : 'border-zinc-700 hover:border-blue-500/50 hover:bg-white/[0.02] bg-white/[0.01]'
            }
          `}
        >
          <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-purple-500/5 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity"></div>
          
          <div className="relative z-10 flex flex-col items-center text-center space-y-4 px-6">
            <div className={`
              p-4 rounded-full transition-transform duration-300 
              ${isDragging ? 'scale-110 bg-blue-500/20' : 'bg-white/5 group-hover:scale-110'}
            `}>
              <TbCloudUpload className={`w-8 h-8 ${isDragging ? 'text-blue-400' : 'text-zinc-400 group-hover:text-blue-400'}`} />
            </div>
            
            <div>
              <p className="text-lg font-medium text-zinc-100">
                Drag and drop your dataset
              </p>
              <p className="text-sm text-zinc-500 mt-1 max-w-sm">
                Supported formats: CSV. File size limit: 50MB.
              </p>
            </div>

            <input type="file" accept=".csv" className="hidden" ref={fileInputRef} onChange={e => processFile(e.target.files[0])} />
            
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="btn-primary px-6 py-2.5 text-sm rounded-full disabled:opacity-50 mt-2"
            >
              {isUploading ? 'Uploading...' : 'Browse files'}
            </button>
          </div>
        </div>
      ) : (
        <div className="glass-panel p-6 sm:p-8 rounded-2xl">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-6">
            <div className="flex gap-4">
              <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-xl shrink-0 h-fit">
                <TbFileSpreadsheet className="w-6 h-6 text-blue-400" />
              </div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-lg font-semibold text-zinc-100 truncate">{lastUpload.table_name?.replace(/_/g, ' ')}</h3>
                  <TbCheck className="w-4 h-4 text-emerald-400" />
                </div>
                <p className="text-sm text-zinc-500 font-data">
                  {lastUpload.row_count?.toLocaleString()} rows • {lastUpload.columns?.length} columns
                </p>
                {businessType && (
                  <div className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/5 border border-white/10 text-xs font-medium text-zinc-300">
                    <span>Domain:</span>
                    <span className="text-blue-400">{businessType}</span>
                  </div>
                )}
              </div>
            </div>
            
            <div className="flex shrink-0">
              <input type="file" accept=".csv" className="hidden" ref={fileInputRef} onChange={e => processFile(e.target.files[0])} />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
                className="text-sm font-medium text-zinc-400 hover:text-white px-4 py-2 rounded-lg border border-white/10 hover:bg-white/5 transition-all w-full sm:w-auto"
              >
                Replace Dataset
              </button>
            </div>
          </div>

          <DataQuality report={lastUpload.data_quality} />

          <div className="mt-6">
            <button
              type="button"
              onClick={() => setShowPreview(v => !v)}
              className="text-sm font-medium text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1"
            >
              {showPreview ? 'Hide Preview' : 'Show Data Preview'}
            </button>
            {showPreview && <DataPreview upload={lastUpload} />}
          </div>
        </div>
      )}

      {error && (
        <div className="mt-4 p-4 rounded-lg bg-red-500/10 border border-red-500/20 flex items-start gap-3 text-red-400 text-sm">
          <TbAlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <p>{error}</p>
        </div>
      )}
    </section>
  );
}
