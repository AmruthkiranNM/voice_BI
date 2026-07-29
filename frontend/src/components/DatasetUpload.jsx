import { useState, useRef, useCallback } from 'react';
import { uploadDataset, deleteDataset } from '../services/api';
import { TbCloudUpload, TbFileSpreadsheet, TbCheck, TbAlertCircle, TbTrash, TbTable } from 'react-icons/tb';

const STEPS = ['Connect', 'Preview', 'Quality check'];

/** Friendly label for a pandas dtype string, as returned by the upload API. */
function friendlyType(dtype) {
  if (!dtype) return 'text';
  if (dtype.startsWith('int') || dtype.startsWith('float')) return 'number';
  if (dtype.startsWith('datetime')) return 'date';
  if (dtype === 'bool') return 'boolean';
  return 'text';
}

function StepIndicator({ step }) {
  return (
    <div className="flex justify-center mb-8">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const done = n < step;
        const active = n === step;
        return (
          <div key={label} className="flex items-center">
            {i > 0 && <div className="w-14 h-px bg-[color:var(--color-border)] mx-3" />}
            <div className="flex items-center gap-2.5">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-[13px] font-bold shrink-0 ${
                  done || active
                    ? 'bg-[#9C4A2A] text-white'
                    : 'border border-[color:var(--color-border)] text-[#9C7A3E]'
                }`}
              >
                {done ? <TbCheck className="w-3.5 h-3.5" /> : n}
              </div>
              <span className={`text-[13px] font-medium ${active ? 'text-zinc-100' : done ? 'text-zinc-300' : 'text-zinc-500'}`}>
                {label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SchemaPreview({ upload }) {
  const columns = upload.columns || [];
  const types = upload.column_types || {};
  const sampleRow = upload.preview_rows?.[0] || {};

  return (
    <div className="mt-6">
      <p className="text-[11px] uppercase tracking-wide font-semibold text-[#9C7A3E] mb-3">
        {upload.table_name?.replace(/_/g, ' ')} · detected schema
      </p>
      <div className="rounded-xl border border-black/10 overflow-hidden">
        <table className="w-full text-xs text-left">
          <thead className="bg-[#FFFFFF] text-zinc-500 border-b border-black/10">
            <tr>
              <th className="px-4 py-2.5 font-medium uppercase tracking-wider text-[10px]">Column</th>
              <th className="px-4 py-2.5 font-medium uppercase tracking-wider text-[10px]">Type</th>
              <th className="px-4 py-2.5 font-medium uppercase tracking-wider text-[10px] text-right">Sample</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-black/5 font-data">
            {columns.map(col => (
              <tr key={col} className="hover:bg-black/[0.02] transition-colors">
                <td className="px-4 py-2 text-zinc-200">{col.replace(/_/g, ' ')}</td>
                <td className="px-4 py-2 text-zinc-500">{friendlyType(types[col])}</td>
                <td className="px-4 py-2 text-right text-zinc-300">
                  {sampleRow[col] ?? <span className="text-zinc-500">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DataPreview({ upload }) {
  if (!upload?.preview_rows?.length) return null;
  const columns = upload.columns || Object.keys(upload.preview_rows[0]);

  return (
    <div className="mt-4 rounded-xl border border-black/10 overflow-hidden">
      <div className="overflow-x-auto max-h-48 scrollbar-thin">
        <table className="w-full text-xs text-left whitespace-nowrap">
          <thead className="sticky top-0 bg-[#FFFFFF] text-zinc-400 border-b border-black/10 z-10">
            <tr>
              {columns.map(col => (
                <th key={col} className="px-4 py-2.5 font-medium uppercase tracking-wider text-[10px]">
                  {col.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-black/5 text-zinc-300">
            {upload.preview_rows.slice(0, 5).map((row, i) => (
              <tr key={i} className="hover:bg-black/5 transition-colors">
                {columns.map(col => (
                  <td key={col} className="px-4 py-2 truncate max-w-[200px]">
                    {row[col] ?? <span className="text-zinc-500">—</span>}
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

function TableList({ tables, onRemoved }) {
  const [removingName, setRemovingName] = useState(null);

  if (!tables?.length) return null;

  const handleRemove = async (name) => {
    setRemovingName(name);
    try {
      await deleteDataset(name);
      onRemoved?.();
    } catch {
      // leave the table visible on failure; user can retry
    } finally {
      setRemovingName(null);
    }
  };

  return (
    <div className="mt-6 space-y-2">
      <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
        Your tables ({tables.length}) — ask questions across all of them, including joins
      </p>
      {tables.map(t => (
        <div key={t.name} className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-black/[0.02] border border-black/5">
          <div className="flex items-center gap-2 min-w-0">
            <TbTable className="w-4 h-4 text-blue-400 shrink-0" />
            <span className="text-sm text-zinc-200 truncate">{t.name.replace(/_/g, ' ')}</span>
            <span className="text-xs text-zinc-500 shrink-0">{t.row_count?.toLocaleString()} rows</span>
          </div>
          <button
            onClick={() => handleRemove(t.name)}
            disabled={removingName === t.name}
            className="text-zinc-500 hover:text-red-400 p-1.5 rounded-md hover:bg-red-500/10 transition-colors disabled:opacity-50"
            title={`Remove ${t.name}`}
          >
            <TbTrash className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

export default function DatasetUpload({ onUploadSuccess, onTableRemoved, onContinueToQuality, tables = [] }) {
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
  const showEmptyState = !lastUpload && tables.length === 0;
  // This freshly-uploaded table's own 3-step journey (Connect → Preview →
  // Quality check). Once other tables exist without a fresh lastUpload,
  // there's no "step" to show — just the compact "add another" state below.
  const step = lastUpload ? 2 : 1;

  return (
    <section className="w-full">
      {lastUpload && <StepIndicator step={step} />}
      {showEmptyState ? (
        <div
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            processFile(e.dataTransfer.files[0]);
          }}
          className={`
            relative group flex flex-col items-center justify-center w-full h-60 sm:h-64
            rounded-2xl border-2 border-dashed transition-colors duration-200
            ${isDragging
              ? 'border-[#9C4A2A] bg-[#9C4A2A]/[0.06]'
              : 'border-black/10 hover:border-[#9C4A2A]/40 hover:bg-black/[0.02]'
            }
          `}
        >
          <div className="relative z-10 flex flex-col items-center text-center space-y-4 px-6">
            <div className={`
              p-4 rounded-full transition-colors duration-200
              ${isDragging ? 'bg-[#9C4A2A]/15' : 'bg-black/5'}
            `}>
              <TbCloudUpload className={`w-7 h-7 ${isDragging ? 'text-[#9C4A2A]' : 'text-zinc-400'}`} />
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
        <div className="surface-card p-6 sm:p-8">
          {lastUpload ? (
            <>
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-6">
                <div className="flex gap-4">
                  <div className="p-3 bg-[#9C4A2A]/10 border border-[#9C4A2A]/20 rounded-xl shrink-0 h-fit">
                    <TbFileSpreadsheet className="w-6 h-6 text-[#9C4A2A]" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-lg font-semibold text-zinc-100 truncate">{lastUpload.table_name?.replace(/_/g, ' ')}</h3>
                      <TbCheck className="w-4 h-4 text-[#3E7A4D]" />
                    </div>
                    <p className="text-sm text-zinc-500 font-data">
                      {lastUpload.row_count?.toLocaleString()} rows • {lastUpload.columns?.length} columns
                    </p>
                    {businessType && (
                      <div className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-black/5 border border-black/10 text-xs font-medium text-zinc-300">
                        <span>Domain:</span>
                        <span className="text-[#9C4A2A]">{businessType}</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex shrink-0">
                  <input type="file" accept=".csv" className="hidden" ref={fileInputRef} onChange={e => processFile(e.target.files[0])} />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isUploading}
                    className="btn-secondary text-sm px-4 py-2 w-full sm:w-auto"
                  >
                    Add Another Table
                  </button>
                </div>
              </div>

              <SchemaPreview upload={lastUpload} />

              <div className="mt-6">
                <button
                  type="button"
                  onClick={() => setShowPreview(v => !v)}
                  className="text-sm font-medium text-[#9C4A2A] hover:text-[#D9A98F] transition-colors flex items-center gap-1"
                >
                  {showPreview ? 'Hide row preview' : 'Show row preview'}
                </button>
                {showPreview && <DataPreview upload={lastUpload} />}
              </div>

              {onContinueToQuality && (
                <button
                  type="button"
                  onClick={onContinueToQuality}
                  className="btn-primary mt-6 px-6 py-2.5 text-sm rounded-lg"
                >
                  Continue to quality check →
                </button>
              )}
            </>
          ) : (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="p-3 bg-[#9C4A2A]/10 border border-[#9C4A2A]/20 rounded-xl shrink-0">
                  <TbTable className="w-6 h-6 text-[#9C4A2A]" />
                </div>
                <p className="text-sm text-zinc-400">
                  {tables.length} table{tables.length === 1 ? '' : 's'} in your workspace
                </p>
              </div>
              <div className="flex shrink-0">
                <input type="file" accept=".csv" className="hidden" ref={fileInputRef} onChange={e => processFile(e.target.files[0])} />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading}
                  className="btn-primary px-4 py-2 text-sm rounded-lg disabled:opacity-50 w-full sm:w-auto"
                >
                  {isUploading ? 'Uploading...' : 'Add Another Table'}
                </button>
              </div>
            </div>
          )}

          <TableList tables={tables} onRemoved={onTableRemoved} />
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
