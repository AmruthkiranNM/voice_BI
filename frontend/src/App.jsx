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
    });
    setResponse(null);
    setError(null);
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
      <Header isProcessing={isLoading} wide={hasResults} />

      {/* Input area — centered */}
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8 flex flex-col gap-8">
        {!datasetInfo.has_data && !hasResults && !isLoading && (
          <section className="text-center space-y-3 pt-6 pb-2">
            <p className="text-xs font-data uppercase tracking-[0.2em] text-[#c8ff4d]">Local · Private · No cloud</p>
            <h2 className="text-3xl sm:text-4xl font-semibold text-white tracking-tight">
              Ask your business data a question
            </h2>
            <p className="text-gray-400 text-sm sm:text-base max-w-md mx-auto">
              Upload a spreadsheet, then ask in plain English — by voice or text. SQL, charts, and a written answer, generated on this machine.
            </p>
          </section>
        )}

        <DatasetUpload onUploadSuccess={handleUploadSuccess} />

        {datasetInfo.has_data && (
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
        )}

        {error && <ErrorPanel error={error} />}

        {isLoading && (
          <div className="flex flex-col items-center gap-4 py-16">
            <div className="w-10 h-10 border-3 border-[#c8ff4d]/20 border-t-[#c8ff4d] rounded-full animate-spin" />
            <p className="text-sm text-gray-400">Working on your question…</p>
          </div>
        )}
      </div>

      {/* Results — full screen width */}
      {hasResults && !isLoading && (
        <div className="w-full px-4 sm:px-6 lg:px-10 xl:px-14 pb-12 border-t border-white/8">
          <div className="max-w-[1600px] mx-auto pt-8">
            <ResultsDashboard
              response={response}
              datasetInfo={datasetInfo}
              settings={settings}
            />
          </div>
        </div>
      )}
    </div>
  );
}
