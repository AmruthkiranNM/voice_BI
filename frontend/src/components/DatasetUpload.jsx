import { useState, useRef, useCallback } from 'react';
import { uploadDataset } from '../services/api';

function DataPreview({ upload }) {
  if (!upload?.preview_rows?.length) return null;

  const columns = upload.columns || Object.keys(upload.preview_rows[0]);

  return (
    <div className="mt-4 w-full">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Data Preview</p>
      <div className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-900/40 max-h-48">
        <table className="w-full text-xs text-left">
          <thead className="bg-gray-800/80 text-gray-400 uppercase sticky top-0">
            <tr>
              {columns.map(col => (
                <th key={col} className="px-3 py-2 font-bold whitespace-nowrap border-b border-gray-700">
                  {col.replace(/_/g, ' ')}
                  {upload.column_types?.[col] && (
                    <span className="block text-[9px] text-gray-500 font-normal normal-case">{upload.column_types[col]}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {upload.preview_rows.map((row, i) => (
              <tr key={i} className="hover:bg-gray-800/30">
                {columns.map(col => (
                  <td key={col} className="px-3 py-2 text-gray-300 whitespace-nowrap font-mono">
                    {row[col] ?? '-'}
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
  const [successMsg, setSuccessMsg] = useState(null);
  const [lastUpload, setLastUpload] = useState(null);
  const fileInputRef = useRef(null);

  const processFile = useCallback(async (file) => {
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Please upload a valid CSV file exported from Excel, Google Sheets, or your POS system.');
      return;
    }

    setIsUploading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const result = await uploadDataset(file);
      setSuccessMsg(result.message);
      setLastUpload(result);
      onUploadSuccess?.(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [onUploadSuccess]);

  const handleFileChange = (e) => processFile(e.target.files[0]);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    processFile(file);
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`w-full rounded-2xl border p-5 shadow-lg glass-panel mb-8 transition-all duration-200
        ${isDragging
          ? 'bg-indigo-950/40 border-indigo-400 border-dashed scale-[1.01]'
          : 'bg-indigo-950/20 border-indigo-500/20 shadow-indigo-500/5'}`}
    >
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-5">
        <div className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl flex-shrink-0 bg-indigo-500/20">
          {isDragging ? '📥' : '📊'}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-[10px] font-bold uppercase tracking-widest text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded">Step 1</span>
            <h3 className="text-lg font-bold text-indigo-300">Upload Your Business Data</h3>
            {lastUpload?.domain && (
              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                {lastUpload.domain.label}
              </span>
            )}
          </div>
          <p className="text-sm text-indigo-100/60">
            Drag & drop a CSV here, or click Upload. Your data stays on your machine.
          </p>

          {lastUpload && (
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className="px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                {lastUpload.row_count?.toLocaleString()} rows
              </span>
              <span className="px-2 py-1 rounded-md bg-gray-800 text-gray-400 border border-gray-700">
                {lastUpload.columns?.length} columns
              </span>
              <span className="px-2 py-1 rounded-md bg-gray-800 text-gray-400 border border-gray-700 font-mono">
                {lastUpload.table_name}
              </span>
            </div>
          )}

          {error && <p className="text-red-400 text-sm mt-2">{error}</p>}
          {successMsg && <p className="text-emerald-400 text-sm mt-2">{successMsg}</p>}
        </div>

        <div className="flex-shrink-0">
          <input type="file" accept=".csv" className="hidden" ref={fileInputRef} onChange={handleFileChange} />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl transition-colors font-semibold text-sm flex items-center gap-2 disabled:opacity-50"
          >
            {isUploading ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>📁 Upload CSV</>
            )}
          </button>
        </div>
      </div>

      <DataPreview upload={lastUpload} />
    </div>
  );
}
