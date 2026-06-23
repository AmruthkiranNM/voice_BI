import { useState, useCallback } from 'react';
import { submitQuery } from './services/api';
import { useQueryHistory } from './hooks/useQueryHistory';

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
  }, []);

  const handleSubmit = useCallback(async (query) => {
    if (!datasetInfo.has_data) {
      setError('Please upload your CSV file before asking questions.');
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
    <div className="min-h-screen bg-[#0a0a08] text-gray-100 font-sans">
      <div className="no-print">
        <Header isProcessing={isLoading} />
      </div>

      <div className="flex flex-col lg:flex-row lg:items-start">
        {/* Left column — chat / query */}
        <aside className="no-print w-full lg:w-[360px] lg:shrink-0 border-b lg:border-b-0 lg:border-r border-white/8 lg:sticky lg:top-14 lg:h-[calc(100vh-3.5rem)] lg:overflow-y-auto px-4 sm:px-6 py-6">
          <p className="text-xs font-data uppercase tracking-[0.2em] text-[#c8ff4d] mb-4">Ask a question</p>

          {datasetInfo.has_data ? (
            <QueryInput
              onSubmit={handleSubmit}
              isLoading={isLoading}
              settings={settings}
              onSettingsChange={setSettings}
              suggestions={datasetInfo.suggestions}
              businessType={datasetInfo.domain?.business_type || datasetInfo.domain?.label}
              history={history}
              onClearHistory={clearHistory}
              onRemoveHistory={removeEntry}
            />
          ) : (
            <div className="border border-white/10 bg-white/[0.02] px-4 py-5 text-sm text-gray-500">
              Upload a spreadsheet to start asking questions.
            </div>
          )}

          {error && <div className="mt-4"><ErrorPanel error={error} /></div>}
        </aside>

        {/* Middle column — upload + live results */}
        <main className="flex-1 min-w-0 px-4 sm:px-6 lg:px-10 py-6 space-y-6">
          <div className="no-print space-y-6">
            {!datasetInfo.has_data && !isLoading && (
              <section className="text-center space-y-3 pt-6 pb-2">
                <h2 className="text-3xl sm:text-4xl font-semibold text-white tracking-tight">
                  Ask your business data a question
                </h2>
                <p className="text-gray-400 text-sm sm:text-base max-w-md mx-auto">
                  Upload a spreadsheet, then ask in plain English — by voice or text. SQL, charts, and a written answer, generated on this machine.
                </p>
              </section>
            )}

            <DatasetUpload onUploadSuccess={handleUploadSuccess} />

            {isLoading && (
              <div className="flex flex-col items-center gap-4 py-16">
                <div className="w-10 h-10 border-3 border-[#c8ff4d]/20 border-t-[#c8ff4d] rounded-full animate-spin" />
                <p className="text-sm text-gray-400">Working on your question…</p>
              </div>
            )}
          </div>

          {hasResults && !isLoading && (
            <ResultsDashboard
              response={response}
              datasetInfo={datasetInfo}
              settings={settings}
              chatMessages={chatMessages}
              onChatMessagesChange={setChatMessages}
            />
          )}
        </main>
      </div>
    </div>
  );
}
