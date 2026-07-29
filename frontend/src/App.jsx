import { useState, useCallback, useEffect, useMemo } from 'react';
import { submitQuery, getDatasets } from './services/api';
import { useQueryHistory } from './hooks/useQueryHistory';
import { TbMenu2, TbDatabase, TbFileSpreadsheet } from 'react-icons/tb';

import Sidebar from './components/Sidebar';
import Header from './components/Header';
import QueryInput, { DEFAULT_SETTINGS } from './components/QueryInput';
import ErrorPanel from './components/ErrorPanel';
import DatasetUpload from './components/DatasetUpload';
import DatabaseConnect from './components/DatabaseConnect';
import ResultsDashboard from './components/ResultsDashboard';
import DataQuality from './components/DataQuality';

export default function App() {
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);

  // Data sources ("sessions"): each is one CSV pool or one DB connection.
  const [sources, setSources] = useState([]);
  const [activeSourceId, setActiveSourceId] = useState(null);
  // Tables selected within the active source. Empty = "Auto" (all of them).
  const [selectedTables, setSelectedTables] = useState(new Set());
  // Preview of the most recently added table (for the pre-query preview card).
  const [lastPreview, setLastPreview] = useState(null);

  const [chatMessages, setChatMessages] = useState([]);
  const { history, addEntry, clearHistory, removeEntry } = useQueryHistory();

  // App Shell State
  const [currentView, setCurrentView] = useState('upload'); // 'upload' or 'dashboard'
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [dataSourceTab, setDataSourceTab] = useState('csv'); // 'csv' or 'database'

  const hasData = sources.length > 0;
  const activeSource = useMemo(
    () => sources.find(s => s.id === activeSourceId) || sources[0] || null,
    [sources, activeSourceId],
  );
  const activeTables = activeSource?.tables || [];

  // The scope sent to the backend: the picked tables, or all of the active
  // source's tables when nothing is explicitly picked ("Auto").
  const scopeTableNames = useMemo(() => {
    if (selectedTables.size > 0) return [...selectedTables];
    return activeTables.map(t => t.name);
  }, [selectedTables, activeTables]);

  // Pull the authoritative source list from the backend after any change.
  const refreshDatasets = useCallback(async () => {
    const data = await getDatasets();
    // Fall back to a single synthetic source if the backend predates sessions.
    const nextSources = data.sources && data.sources.length
      ? data.sources
      : (data.tables?.length
          ? [{ id: 'local_files', label: 'Uploaded files', type: 'csv', tables: data.tables, domain: data.domain, suggestions: data.suggestions || [] }]
          : []);
    setSources(nextSources);
    setActiveSourceId(prev => {
      if (prev && nextSources.some(s => s.id === prev)) return prev;
      return nextSources[0]?.id || null;
    });
    return data;
  }, []);

  useEffect(() => { refreshDatasets(); }, [refreshDatasets]);

  // Switching source always resets the table selection to Auto.
  const selectSource = useCallback((sourceId) => {
    setActiveSourceId(sourceId);
    setSelectedTables(new Set());
    setResponse(null);
    setChatMessages([]);
  }, []);

  const afterIngest = useCallback(async (firstTable, newSourceId) => {
    if (firstTable) {
      setLastPreview({
        sourceId: newSourceId,
        tableName: firstTable.table_name,
        rowCount: firstTable.row_count,
        columns: firstTable.columns || [],
        preview_rows: firstTable.preview_rows || [],
        dataQuality: firstTable.data_quality || null,
      });
    }
    await refreshDatasets();
    if (newSourceId) setActiveSourceId(newSourceId);
    setSelectedTables(new Set());
    setResponse(null);
    setError(null);
    setChatMessages([]);
    setCurrentView('dashboard');
  }, [refreshDatasets]);

  const handleUploadSuccess = useCallback(
    (uploadResult) => afterIngest(uploadResult, uploadResult.source_id || 'local_files'),
    [afterIngest],
  );

  const handleImportSuccess = useCallback(
    (importResult) => afterIngest(importResult.imported?.[0], importResult.source_id),
    [afterIngest],
  );

  const handleTableRemoved = useCallback(async () => {
    await refreshDatasets();
    setSelectedTables(new Set());
  }, [refreshDatasets]);

  const toggleTable = useCallback((name) => {
    setSelectedTables(prev => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }, []);

  const handleSubmit = useCallback(async (query) => {
    if (!hasData) {
      setError('Please connect a data source before asking questions.');
      setCurrentView('upload');
      return;
    }

    setIsLoading(true);
    setError(null);
    setResponse(null);

    try {
      const result = await submitQuery(query, {
        model: settings.model || null,
        tableNames: scopeTableNames,
        cacheMode: settings.cacheMode,
        fastMode: settings.fastMode,
        skipInsight: settings.skipInsight,
      });
      setResponse(result);
      if (result.success) {
        addEntry({
          query,
          rowCount: result.result?.row_count,
          summary: result.insight?.slice(0, 100),
        });
      } else {
        setError(result.error);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [settings, hasData, scopeTableNames, addEntry]);

  const hasResults = response && (
    response.sql || response.result?.row_count > 0 || response.insight
  );

  // Preview only makes sense for the source it came from.
  const showPreview = lastPreview && lastPreview.sourceId === activeSource?.id;

  return (
    <div className="flex h-screen bg-[#1C1917] text-zinc-100 font-sans overflow-hidden">

      {/* Sidebar Navigation */}
      <Sidebar
        currentView={currentView}
        onViewChange={setCurrentView}
        isMobileOpen={isMobileOpen}
        setIsMobileOpen={setIsMobileOpen}
        sources={sources}
        activeSourceId={activeSource?.id || null}
        onSelectSource={selectSource}
        onDatasetsChanged={handleTableRemoved}
        isProcessing={isLoading}
      />

      {/* Main Workspace */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden relative">

        {/* Top bar — just a mobile menu toggle and current source, no chrome */}
        <header className="h-14 flex items-center justify-between px-4 sm:px-10 lg:hidden shrink-0">
          <button
            onClick={() => setIsMobileOpen(true)}
            className="p-2 -ml-2 text-zinc-400 hover:text-white rounded-md"
            aria-label="Open menu"
          >
            <TbMenu2 className="w-5 h-5" />
          </button>
          <Header isProcessing={isLoading} />
        </header>

        {/* Scrollable Content Area */}
        <main className="flex-1 overflow-y-auto px-4 sm:px-10 py-6 sm:py-10 relative">

          <div className="max-w-6xl mx-auto space-y-10 pb-16">

            {/* View: Data Source / Upload */}
            {currentView === 'upload' && (
              <div className="animate-in max-w-2xl mx-auto">
                <div className="text-center space-y-3 pt-6 pb-10">
                  <h1 className="text-4xl sm:text-[2.75rem] font-semibold text-white tracking-tight">
                    Connect your data
                  </h1>
                  <p className="text-zinc-400 text-base max-w-md mx-auto leading-relaxed">
                    Upload a spreadsheet or connect a database. Everything below stays on your machine.
                  </p>
                </div>

                <div className="flex justify-center gap-1 mb-8 p-1 ask-bar w-fit mx-auto">
                  <button
                    onClick={() => setDataSourceTab('csv')}
                    className={`flex items-center gap-2 px-5 py-2 text-sm font-medium rounded-full transition-colors ${
                      dataSourceTab === 'csv' ? 'active-pill' : 'text-zinc-400 hover:text-white'
                    }`}
                  >
                    <TbFileSpreadsheet className="w-4 h-4" /> Upload CSV
                  </button>
                  <button
                    onClick={() => setDataSourceTab('database')}
                    className={`flex items-center gap-2 px-5 py-2 text-sm font-medium rounded-full transition-colors ${
                      dataSourceTab === 'database' ? 'active-pill' : 'text-zinc-400 hover:text-white'
                    }`}
                  >
                    <TbDatabase className="w-4 h-4" /> Connect Database
                  </button>
                </div>

                {dataSourceTab === 'csv' ? (
                  <DatasetUpload
                    onUploadSuccess={handleUploadSuccess}
                    onTableRemoved={handleTableRemoved}
                    tables={sources.find(s => s.type === 'csv')?.tables || []}
                  />
                ) : (
                  <DatabaseConnect onImportSuccess={handleImportSuccess} />
                )}

                {hasData && (
                  <div className="mt-10 text-center">
                    <button
                      onClick={() => setCurrentView('dashboard')}
                      className="btn-primary px-6 py-3 text-sm rounded-full"
                    >
                      Go to Analysis Dashboard →
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* View: Dashboard & Analysis */}
            {currentView === 'dashboard' && (
              <div className="animate-in space-y-10">

                {!hasResults && (
                  <div className="text-center pt-2 pb-2 max-w-2xl mx-auto">
                    <h1 className="text-3xl sm:text-[2.25rem] font-semibold text-white tracking-tight">
                      What do you want to know?
                    </h1>
                    {activeSource && (
                      <p className="text-zinc-500 text-sm mt-2 flex items-center justify-center gap-1.5">
                        {activeSource.type === 'csv'
                          ? <TbFileSpreadsheet className="w-3.5 h-3.5" />
                          : <TbDatabase className="w-3.5 h-3.5" />}
                        {activeSource.label}
                      </p>
                    )}
                  </div>
                )}

                {/* Query-scope selector — pick one or more tables from the
                    ACTIVE source, or Auto (all of them). Only shown when the
                    active source has more than one table. */}
                {activeTables.length > 1 && (
                  <div className="flex flex-wrap items-center justify-center gap-2 -mt-6 -mb-2">
                    <span className="text-xs text-zinc-500 mr-1">Scope:</span>
                    <button
                      onClick={() => setSelectedTables(new Set())}
                      className={`text-xs px-3 py-1.5 rounded-full transition-colors ${
                        selectedTables.size === 0
                          ? 'active-pill'
                          : 'border border-white/10 text-zinc-400 hover:text-white hover:bg-white/5'
                      }`}
                      title="Let the AI use every table in this source, including joins"
                    >
                      Auto (all)
                    </button>
                    {activeTables.map(t => {
                      const on = selectedTables.has(t.name);
                      return (
                        <button
                          key={t.name}
                          onClick={() => toggleTable(t.name)}
                          className={`text-xs px-3 py-1.5 rounded-full transition-colors ${
                            on ? 'active-pill' : 'border border-white/10 text-zinc-400 hover:text-white hover:bg-white/5'
                          }`}
                          title={on ? 'Click to remove from scope' : 'Click to add to scope'}
                        >
                          {t.name.replace(/_/g, ' ')}
                        </button>
                      );
                    })}
                    {selectedTables.size > 1 && (
                      <span className="text-[11px] text-[#EFC3AC]/70">
                        {selectedTables.size} tables · joins allowed
                      </span>
                    )}
                  </div>
                )}

                {/* Ask bar */}
                {hasData ? (
                  <QueryInput
                    onSubmit={handleSubmit}
                    isLoading={isLoading}
                    settings={settings}
                    onSettingsChange={setSettings}
                    suggestions={!hasResults ? (activeSource?.suggestions || []) : []}
                    businessType={activeSource?.domain?.business_type || activeSource?.domain?.label}
                    history={history}
                    onClearHistory={clearHistory}
                    onRemoveHistory={removeEntry}
                  />
                ) : (
                  <div className="text-center py-6 text-zinc-500 text-sm surface-card max-w-xl mx-auto">
                    Please connect a data source first.
                    <button
                      onClick={() => setCurrentView('upload')}
                      className="ml-2 text-[#D97757] hover:text-[#EFC3AC] underline underline-offset-4"
                    >
                      Go to Data Source
                    </button>
                  </div>
                )}

                {/* Show Data Preview and Quality before any query is run */}
                {!hasResults && showPreview && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {lastPreview.dataQuality && (
                      <DataQuality quality={lastPreview.dataQuality} />
                    )}
                    {lastPreview.preview_rows?.length > 0 && (
                      <div className="surface-card p-6 animate-in">
                        <h3 className="text-sm font-semibold text-zinc-100 mb-4 flex items-center gap-2">
                          <TbFileSpreadsheet className="w-4 h-4 text-[#D97757]" />
                          Data Preview
                          <span className="text-zinc-500 font-normal text-xs ml-1">
                            {lastPreview.tableName?.replace(/_/g, ' ')} · {lastPreview.rowCount?.toLocaleString()} rows
                          </span>
                        </h3>
                        <div className="overflow-x-auto max-h-64 scrollbar-thin rounded-xl border border-white/10">
                          <table className="w-full text-xs text-left whitespace-nowrap">
                            <thead className="sticky top-0 bg-[#262220] text-zinc-400 border-b border-white/10 z-10">
                              <tr>
                                {lastPreview.columns.map(col => (
                                  <th key={col} className="px-4 py-3 font-medium uppercase tracking-wider text-[10px]">
                                    {col.replace(/_/g, ' ')}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-white/5 text-zinc-300">
                              {lastPreview.preview_rows.slice(0, 8).map((row, i) => (
                                <tr key={i} className="hover:bg-white/5 transition-colors">
                                  {lastPreview.columns.map(col => (
                                    <td key={col} className="px-4 py-2.5 truncate max-w-[200px]">
                                      {row[col] ?? <span className="text-zinc-500">—</span>}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {error && <ErrorPanel error={error} />}

                {isLoading && (
                  <div className="flex flex-col items-center gap-5 py-20">
                    <div className="w-8 h-8 border-2 border-[#D97757]/25 border-t-[#D97757] rounded-full animate-spin"></div>
                    <div className="text-center space-y-1">
                      <p className="text-sm font-medium text-zinc-200">Thinking through your data…</p>
                      <p className="text-xs text-zinc-500">Generating SQL, running it, and building the visuals</p>
                    </div>
                  </div>
                )}

                {hasResults && !isLoading && (
                  <ResultsDashboard
                    response={response}
                    datasetInfo={{
                      has_data: hasData,
                      domain: activeSource?.domain || null,
                      tableName: selectedTables.size === 1 ? [...selectedTables][0] : null,
                      tableNames: scopeTableNames,
                    }}
                    settings={settings}
                    chatMessages={chatMessages}
                    onChatMessagesChange={setChatMessages}
                  />
                )}
              </div>
            )}

          </div>
        </main>
      </div>
    </div>
  );
}
