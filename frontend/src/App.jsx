import { useState, useCallback } from 'react';
import { submitQuery } from './services/api';
import { useQueryHistory } from './hooks/useQueryHistory';
import { TbMenu2 } from 'react-icons/tb';

import Sidebar from './components/Sidebar';
import Header from './components/Header';
import QueryInput, { DEFAULT_SETTINGS } from './components/QueryInput';
import ErrorPanel from './components/ErrorPanel';
import DatasetUpload from './components/DatasetUpload';
import ResultsDashboard from './components/ResultsDashboard';

export default function App() {
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [datasetInfo, setDatasetInfo] = useState({ has_data: false, suggestions: [], domain: null });
  const [chatMessages, setChatMessages] = useState([]);
  const { history, addEntry, clearHistory, removeEntry } = useQueryHistory();
  
  // App Shell State
  const [currentView, setCurrentView] = useState('upload'); // 'upload' or 'dashboard'
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  const handleUploadSuccess = useCallback((uploadResult) => {
    setDatasetInfo({
      has_data: true,
      suggestions: uploadResult.suggestions || [],
      domain: uploadResult.domain || null,
      tableName: uploadResult.table_name,
      rowCount: uploadResult.row_count,
      columns: uploadResult.columns || [],
      columnTypes: uploadResult.column_types || {},
      dataQuality: uploadResult.data_quality || null,
    });
    setResponse(null);
    setError(null);
    setChatMessages([]);
    setCurrentView('dashboard');
  }, []);

  const handleSubmit = useCallback(async (query) => {
    if (!datasetInfo.has_data) {
      setError('Please upload your CSV file before asking questions.');
      setCurrentView('upload');
      return;
    }

    setIsLoading(true);
    setError(null);
    setResponse(null);

    try {
      const result = await submitQuery(query, {
        model: settings.model || null,
        tableName: datasetInfo.tableName || null,
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
  }, [settings, datasetInfo.has_data, datasetInfo.tableName, addEntry]);

  const hasResults = response && (
    response.sql || response.result?.row_count > 0 || response.insight
  );

  return (
    <div className="flex h-screen bg-[#09090b] text-zinc-100 font-sans overflow-hidden">
      
      {/* Sidebar Navigation */}
      <Sidebar 
        currentView={currentView}
        onViewChange={setCurrentView}
        isMobileOpen={isMobileOpen}
        setIsMobileOpen={setIsMobileOpen}
      />

      {/* Main Workspace */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden relative">
        
        {/* Top Header */}
        <header className="h-16 flex items-center justify-between px-4 sm:px-8 border-b border-white/5 bg-[#09090b]/80 backdrop-blur-md z-10 shrink-0">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => setIsMobileOpen(true)}
              className="lg:hidden p-2 -ml-2 text-zinc-400 hover:text-white rounded-md"
            >
              <TbMenu2 className="w-5 h-5" />
            </button>
            <div className="text-sm font-medium text-zinc-300 capitalize tracking-wide flex items-center gap-2">
              <span className="text-zinc-500 hidden sm:inline">Workspace /</span>
              <span className="text-zinc-100">{currentView === 'upload' ? 'Data Source' : 'Analysis Dashboard'}</span>
            </div>
          </div>
          <Header isProcessing={isLoading} />
        </header>

        {/* Scrollable Content Area */}
        <main className="flex-1 overflow-y-auto px-4 sm:px-8 py-8 relative">
          
          <div className="max-w-7xl mx-auto space-y-8 pb-12">
            
            {/* View: Data Source / Upload */}
            {currentView === 'upload' && (
              <div className="animate-in max-w-4xl mx-auto">
                <div className="text-center space-y-4 pt-4 pb-8">
                  <h1 className="text-3xl sm:text-4xl font-semibold text-white tracking-tight">
                    Connect your data
                  </h1>
                  <p className="text-zinc-400 text-base max-w-lg mx-auto leading-relaxed">
                    Upload your business spreadsheet to securely analyze trends, ask natural language questions, and generate instant BI dashboards.
                  </p>
                </div>
                
                <DatasetUpload onUploadSuccess={handleUploadSuccess} />
                
                {datasetInfo.has_data && (
                  <div className="mt-8 text-center">
                    <button 
                      onClick={() => setCurrentView('dashboard')}
                      className="btn-primary px-6 py-3 text-sm"
                    >
                      Go to Analysis Dashboard →
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* View: Dashboard & Analysis */}
            {currentView === 'dashboard' && (
              <div className="animate-in space-y-8">
                
                {/* AI Command Center */}
                <div className="glass-panel p-1 rounded-2xl sticky top-0 z-20 shadow-2xl shadow-black/50">
                  <div className="bg-[#18181b] rounded-xl p-4 sm:p-5 border border-white/5">
                    {datasetInfo.has_data ? (
                      <QueryInput
                        onSubmit={handleSubmit}
                        isLoading={isLoading}
                        settings={settings}
                        onSettingsChange={setSettings}
                        suggestions={!hasResults ? datasetInfo.suggestions : []}
                        businessType={datasetInfo.domain?.business_type || datasetInfo.domain?.label}
                        history={history}
                        onClearHistory={clearHistory}
                        onRemoveHistory={removeEntry}
                      />
                    ) : (
                      <div className="text-center py-6 text-zinc-500 text-sm">
                        Please connect a data source first.
                        <button 
                          onClick={() => setCurrentView('upload')}
                          className="ml-2 text-blue-400 hover:text-blue-300 underline underline-offset-4"
                        >
                          Go to Data Source
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {error && <ErrorPanel error={error} />}

                {isLoading && (
                  <div className="flex flex-col items-center gap-6 py-20">
                    <div className="relative w-12 h-12 flex items-center justify-center">
                      <div className="absolute inset-0 border-4 border-blue-500/20 rounded-full"></div>
                      <div className="absolute inset-0 border-4 border-blue-500 rounded-full border-t-transparent animate-spin"></div>
                      <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse"></div>
                    </div>
                    <div className="text-center space-y-2">
                      <p className="text-sm font-medium text-blue-400 animate-pulse">AI is analyzing your data...</p>
                      <p className="text-xs text-zinc-500">Generating insights and visualizations</p>
                    </div>
                  </div>
                )}

                {hasResults && !isLoading && (
                  <ResultsDashboard
                    response={response}
                    datasetInfo={datasetInfo}
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
