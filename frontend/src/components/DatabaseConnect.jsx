import { useState, useCallback } from 'react';
import { testDbConnection, importDbTables } from '../services/api';
import { TbDatabase, TbPlugConnected, TbAlertCircle, TbCheck, TbLoader2, TbTable, TbEye, TbEyeOff } from 'react-icons/tb';

const PLACEHOLDER = 'postgresql://user:password@host:5432/dbname';

export default function DatabaseConnect({ onImportSuccess }) {
  const [connectionString, setConnectionString] = useState('');
  const [isTesting, setIsTesting] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState(null);
  const [discoveredTables, setDiscoveredTables] = useState(null); // null = not tested yet
  const [selected, setSelected] = useState(new Set());
  const [showConnectionString, setShowConnectionString] = useState(false);

  const handleTest = useCallback(async () => {
    if (!connectionString.trim()) return;
    setIsTesting(true);
    setError(null);
    setDiscoveredTables(null);
    try {
      const result = await testDbConnection(connectionString.trim());
      setDiscoveredTables(result.tables || []);
      setSelected(new Set((result.tables || []).map(t => t.name)));
    } catch (err) {
      setError(err.message);
    } finally {
      setIsTesting(false);
    }
  }, [connectionString]);

  const toggleTable = (name) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  };

  const handleImport = useCallback(async () => {
    if (selected.size === 0) return;
    setIsImporting(true);
    setError(null);
    try {
      const result = await importDbTables(connectionString.trim(), Array.from(selected));
      if (result.errors?.length > 0 && result.imported?.length === 0) {
        setError(result.errors.map(e => `${e.table}: ${e.error}`).join('; '));
        return;
      }
      onImportSuccess?.(result);
      setConnectionString('');
      setDiscoveredTables(null);
      setSelected(new Set());
    } catch (err) {
      setError(err.message);
    } finally {
      setIsImporting(false);
    }
  }, [connectionString, selected, onImportSuccess]);

  return (
    <section className="w-full">
      <div className="glass-panel p-6 sm:p-8 rounded-2xl">
        <div className="flex items-start gap-4 mb-6">
          <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-xl shrink-0">
            <TbDatabase className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-zinc-100">Connect a database</h3>
            <p className="text-sm text-zinc-500 mt-1 max-w-lg leading-relaxed">
              Postgres-compatible sources (Supabase, Neon, RDS, or plain Postgres). Selected
              tables are imported into your local workspace — analysis still runs 100% locally
              afterward, and your credentials are never stored.
            </p>
          </div>
        </div>

        <label htmlFor="db-connection-string" className="block text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">
          Connection string
        </label>
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <input
              id="db-connection-string"
              type={showConnectionString ? 'text' : 'password'}
              value={connectionString}
              onChange={e => { setConnectionString(e.target.value); setDiscoveredTables(null); }}
              placeholder={PLACEHOLDER}
              className="w-full bg-black/30 border border-black/10 rounded-lg pl-4 pr-10 py-2.5 text-sm text-zinc-200 placeholder:text-zinc-600 font-data focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40"
              autoComplete="off"
            />
            <button
              type="button"
              onClick={() => setShowConnectionString(v => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-zinc-500 hover:text-zinc-300 rounded-md hover:bg-black/5"
              aria-label={showConnectionString ? 'Hide connection string' : 'Show connection string'}
              tabIndex={-1}
            >
              {showConnectionString ? <TbEyeOff className="w-4 h-4" /> : <TbEye className="w-4 h-4" />}
            </button>
          </div>
          <button
            onClick={handleTest}
            disabled={isTesting || !connectionString.trim()}
            className="btn-primary px-5 py-2.5 text-sm rounded-lg disabled:opacity-50 flex items-center justify-center gap-2 shrink-0"
          >
            {isTesting ? <TbLoader2 className="w-4 h-4 animate-spin" /> : <TbPlugConnected className="w-4 h-4" />}
            {isTesting ? 'Testing…' : 'Test Connection'}
          </button>
        </div>

        {error && (
          <div className="mt-4 p-4 rounded-lg bg-red-500/10 border border-red-500/20 flex items-start gap-3 text-red-400 text-sm">
            <TbAlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
            <p className="break-words">{error}</p>
          </div>
        )}

        {discoveredTables && (
          <div className="mt-6">
            {discoveredTables.length === 0 ? (
              <p className="text-sm text-zinc-500">No tables found in the public schema.</p>
            ) : (
              <>
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
                    {discoveredTables.length} table{discoveredTables.length === 1 ? '' : 's'} found — select which to import
                  </p>
                  <TbCheck className="w-4 h-4 text-[#3E7A4D]" />
                </div>
                <div className="space-y-2 max-h-64 overflow-y-auto scrollbar-thin pr-1">
                  {discoveredTables.map(t => (
                    <label
                      key={t.name}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-black/[0.02] border border-black/5 hover:bg-black/5 cursor-pointer transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(t.name)}
                        onChange={() => toggleTable(t.name)}
                        className="accent-blue-500 w-4 h-4 shrink-0"
                      />
                      <TbTable className="w-4 h-4 text-blue-400 shrink-0" />
                      <span className="text-sm text-zinc-200 truncate flex-1">{t.name}</span>
                      <span className="text-xs text-zinc-500 shrink-0">~{t.estimated_rows?.toLocaleString()} rows</span>
                    </label>
                  ))}
                </div>

                <button
                  onClick={handleImport}
                  disabled={isImporting || selected.size === 0}
                  className="btn-primary mt-4 w-full sm:w-auto px-6 py-2.5 text-sm rounded-lg disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {isImporting && <TbLoader2 className="w-4 h-4 animate-spin" />}
                  {isImporting ? 'Importing…' : `Import ${selected.size} table${selected.size === 1 ? '' : 's'}`}
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
