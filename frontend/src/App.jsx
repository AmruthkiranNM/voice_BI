import { useState, useCallback, useEffect, useMemo } from 'react';
import { submitQuery, getDatasets, getToken, setToken } from './services/api';
import { useQueryHistory } from './hooks/useQueryHistory';
import { TbMenu2, TbDatabase, TbFileSpreadsheet } from 'react-icons/tb';

import Sidebar from './components/Sidebar';
import Header from './components/Header';
import QueryInput, { DEFAULT_SETTINGS } from './components/QueryInput';
import ErrorPanel from './components/ErrorPanel';
import DatasetUpload from './components/DatasetUpload';
import DatabaseConnect from './components/DatabaseConnect';
import ResultsDashboard from './components/ResultsDashboard';
import DataQualityPage from './components/DataQualityPage';
import LoginPage from './components/LoginPage';
import SkeletonLoader from './components/SkeletonLoader';
import AIProcessingScreen from './components/AIProcessingScreen';
import TablePreviewCard from './components/TablePreviewCard';
import TabbedTables from './components/TabbedTables';
import { useTablePreviews } from './hooks/useTablePreviews';
import { useTheme } from './hooks/useTheme';
import { analyzeComplexity } from './utils/complexityAnalyzer';

export default function App() {
  const { theme, toggleTheme } = useTheme();
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    if (getToken()) {
      // Token exists from a previous session; the user object isn't
      // persisted, so a minimal placeholder is enough to unlock the app —
      // any expired/invalid token still gets rejected on the first API call.
      setUser({ email: null });
    }
    setAuthChecked(true);

    const onLogout = () => setUser(null);
    window.addEventListener('auth:logout', onLogout);
    return () => window.removeEventListener('auth:logout', onLogout);
  }, []);

  const handleAuthenticated = useCallback((token, authedUser) => {
    setToken(token);
    setUser(authedUser);
  }, []);

  const handleLogout = useCallback(() => {
    setToken(null);
    setUser(null);
    setSources([]);
    setActiveSourceId(null);
    setResponse(null);
    setChatMessages([]);
  }, []);

  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [isLoading, setIsLoading] = useState(false);
  const [isSimulatingLoading, setIsSimulatingLoading] = useState(false);
  const [pendingResponse, setPendingResponse] = useState(null);
  const [pendingError, setPendingError] = useState(null);
  const [currentQuery, setCurrentQuery] = useState('');
  // Faked pipeline duration (seconds) matching the AI processing loader's
  // simulated timing, so the results page doesn't reveal the real (much
  // faster, API-backed) response time.
  const [fakePipelineSeconds, setFakePipelineSeconds] = useState(null);
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
  const { history, addEntry, clearHistory, removeEntry, pinned, togglePin } = useQueryHistory();

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
  const activeTableNames = useMemo(() => activeTables.map(t => t.name), [activeTables]);

  // The scope sent to the backend: the picked tables, or all of the active
  // source's tables when nothing is explicitly picked ("Auto").
  const scopeTableNames = useMemo(() => {
    if (selectedTables.size > 0) return [...selectedTables];
    return activeTableNames;
  }, [selectedTables, activeTableNames]);

  // Sample rows + quality report for every table in the active source (not
  // just the one most recently uploaded), used by the pre-results preview
  // and the Data Quality tab.
  const { previews: tablePreviews } = useTablePreviews(activeTableNames);

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

  useEffect(() => { if (user) refreshDatasets(); }, [user, refreshDatasets]);

  // Switching source always resets the table selection to Auto.
  const selectSource = useCallback((sourceId) => {
    setActiveSourceId(sourceId);
    setSelectedTables(new Set());
    setResponse(null);
    setChatMessages([]);
  }, []);

  const afterIngest = useCallback(async (firstTable, newSourceId, navigate = true) => {
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
    if (navigate) setCurrentView('dashboard');
  }, [refreshDatasets]);

  // Both CSV and database connections stay on the Data Source view after
  // ingesting — one consistent "connect, then explicitly move on" flow
  // instead of CSV pausing for a preview while DB connections used to jump
  // straight to the dashboard.
  const handleUploadSuccess = useCallback(
    (uploadResult) => afterIngest(uploadResult, uploadResult.source_id || 'local_files', false),
    [afterIngest],
  );

  const handleImportSuccess = useCallback(
    (importResult) => afterIngest(importResult.imported?.[0], importResult.source_id, false),
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
    setIsSimulatingLoading(true);
    setCurrentQuery(query);
    setFakePipelineSeconds(analyzeComplexity(query).targetDurationMs / 1000);
    setError(null);
    setResponse(null);
    setPendingResponse(null);
    setPendingError(null);

    try {
      const result = await submitQuery(query, {
        model: settings.model || null,
        tableNames: scopeTableNames,
        cacheMode: settings.cacheMode,
        fastMode: settings.fastMode,
        skipInsight: settings.skipInsight,
      });
      if (result?.metadata?.cache_hit) {
        // Already-cached answers come back near-instantly — skip the fake
        // "AI thinking" loader instead of sitting through the full simulation.
        setIsSimulatingLoading(false);
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
      } else {
        setPendingResponse(result);
      }
    } catch (err) {
      setPendingError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [settings, hasData, scopeTableNames, addEntry]);

  const handleSimulatedLoadingComplete = useCallback(() => {
    setIsSimulatingLoading(false);
    
    if (pendingError) {
      setError(pendingError);
    } else if (pendingResponse) {
      setResponse(pendingResponse);
      if (pendingResponse.success) {
        addEntry({
          query: currentQuery,
          rowCount: pendingResponse.result?.row_count,
          summary: pendingResponse.insight?.slice(0, 100),
        });
      } else {
        setError(pendingResponse.error);
      }
    }
  }, [pendingError, pendingResponse, currentQuery, addEntry]);

  const hasResults = response && (
    response.sql || response.result?.row_count > 0 || response.insight
  );

  // Preview only makes sense for the source it came from.
  const showPreview = lastPreview && lastPreview.sourceId === activeSource?.id;

  if (!authChecked) return null;
  if (!user) return <LoginPage onAuthenticated={handleAuthenticated} />;

  return (
    <div className="flex h-screen bg-bg text-zinc-100 font-sans overflow-hidden">

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
        user={user}
        onLogout={handleLogout}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      {/* Main Workspace */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden relative">

        {/* Top bar — just a mobile menu toggle and current source, no chrome */}
        <header className="h-14 flex items-center justify-between px-4 sm:px-10 lg:hidden shrink-0">
          <button
            onClick={() => setIsMobileOpen(true)}
            className="p-2 -ml-2 text-zinc-400 hover:text-zinc-100 rounded-md"
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
                  <h1 className="text-4xl sm:text-[2.75rem] font-semibold text-zinc-100 tracking-tight">
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
                      dataSourceTab === 'csv' ? 'active-pill' : 'text-zinc-400 hover:text-zinc-100'
                    }`}
                  >
                    <TbFileSpreadsheet className="w-4 h-4" /> Upload CSV
                  </button>
                  <button
                    onClick={() => setDataSourceTab('database')}
                    className={`flex items-center gap-2 px-5 py-2 text-sm font-medium rounded-full transition-colors ${
                      dataSourceTab === 'database' ? 'active-pill' : 'text-zinc-400 hover:text-zinc-100'
                    }`}
                  >
                    <TbDatabase className="w-4 h-4" /> Connect Database
                  </button>
                </div>

                {dataSourceTab === 'csv' ? (
                  <DatasetUpload
                    onUploadSuccess={handleUploadSuccess}
                    onTableRemoved={handleTableRemoved}
                    onContinueToQuality={() => setCurrentView('quality')}
                    tables={sources.find(s => s.type === 'csv')?.tables || []}
                  />
                ) : (
                  <DatabaseConnect onImportSuccess={handleImportSuccess} />
                )}

                {/* Single "move on" CTA — hidden while the CSV flow above is
                    already showing its own "Continue to quality check" button,
                    so there's never more than one obvious next step at once. */}
                {hasData && !(dataSourceTab === 'csv' && showPreview) && (
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
                    <h1 className="text-3xl sm:text-[2.25rem] font-semibold text-zinc-100 tracking-tight">
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
                  <div className="flex flex-wrap items-center justify-center gap-2 -mt-2">
                    <span className="text-xs text-zinc-500 mr-1">Scope:</span>
                    <button
                      onClick={() => setSelectedTables(new Set())}
                      className={`text-xs px-3 py-1.5 rounded-full transition-colors ${
                        selectedTables.size === 0
                          ? 'active-pill'
                          : 'border border-black/10 text-zinc-400 hover:text-zinc-100 hover:bg-black/5'
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
                            on ? 'active-pill' : 'border border-black/10 text-zinc-400 hover:text-zinc-100 hover:bg-black/5'
                          }`}
                          title={on ? 'Click to remove from scope' : 'Click to add to scope'}
                        >
                          {t.name.replace(/_/g, ' ')}
                        </button>
                      );
                    })}
                    {selectedTables.size > 1 && (
                      <span className="text-[11px] text-[#D9A98F]/70">
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
                    insight={response?.insight}
                    settings={settings}
                    onSettingsChange={setSettings}
                    suggestions={!hasResults ? (activeSource?.suggestions || []) : []}
                    businessType={activeSource?.domain?.business_type || activeSource?.domain?.label}
                    history={history}
                    onClearHistory={clearHistory}
                    onRemoveHistory={removeEntry}
                    pinned={pinned}
                    onTogglePin={togglePin}
                  />
                ) : (
                  <div className="text-center py-6 text-zinc-500 text-sm surface-card max-w-xl mx-auto">
                    Please connect a data source first.
                    <button
                      onClick={() => setCurrentView('upload')}
                      className="ml-2 text-[#9C4A2A] hover:text-[#D9A98F] underline underline-offset-4"
                    >
                      Go to Data Source
                    </button>
                  </div>
                )}

                {/* Data Preview — every table in this source, switchable via
                    tabs instead of stacking one card per table */}
                {!hasResults && activeTables.length > 0 && (
                  <TabbedTables
                    tableNames={activeTableNames}
                    previews={tablePreviews}
                    renderTable={(name, preview) => <TablePreviewCard preview={preview} />}
                  />
                )}

                {error && <ErrorPanel error={error} />}

                {isLoading && !isSimulatingLoading && <SkeletonLoader />}

                {isSimulatingLoading && (
                  <AIProcessingScreen 
                    query={currentQuery}
                    isBackendFinished={!isLoading}
                    onComplete={handleSimulatedLoadingComplete}
                  />
                )}

                {hasResults && !isLoading && !isSimulatingLoading && (
                  <ResultsDashboard
                    response={response}
                    fakePipelineSeconds={fakePipelineSeconds}
                    sourceLabel={activeSource?.label}
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

            {/* View: Data Quality */}
            {currentView === 'quality' && (
              <DataQualityPage
                tableNames={activeTableNames}
                onContinue={hasData ? () => setCurrentView('dashboard') : null}
              />
            )}

          </div>
        </main>
      </div>
    </div>
  );
}
