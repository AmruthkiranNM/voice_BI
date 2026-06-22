import { useState, useCallback } from 'react';
import { submitQuery } from './services/api';
import { useQueryHistory } from './hooks/useQueryHistory';

import Header from './components/Header';
import QueryInput, { DEFAULT_SETTINGS } from './components/QueryInput';
import ResultTable from './components/ResultTable';
import InsightPanel from './components/InsightPanel';
import ChartPanel from './components/ChartPanel';
import ErrorPanel from './components/ErrorPanel';
import DatasetUpload from './components/DatasetUpload';
import TechnicalDetails from './components/TechnicalDetails';

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

  const plan = response?.metadata?.plan || null;
  const metadata = response?.metadata || null;
  const sql = response?.sql || null;
  const result = response?.result || null;
  const insight = response?.insight || null;
  const warnings = metadata?.validation_warnings || [];
  const intent = plan?.intent || null;
  const hasResults = response && (sql || result?.row_count > 0 || insight);

  return (
    <div className="min-h-screen bg-[#030712] text-gray-100 font-sans">
      <Header isProcessing={isLoading} />

      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 flex flex-col gap-8">

        {/* Hero — only before upload */}
        {!datasetInfo.has_data && !hasResults && !isLoading && (
          <section className="text-center space-y-3 pt-4 pb-2">
            <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight">
              Ask questions about your business data
            </h2>
            <p className="text-gray-400 text-sm sm:text-base max-w-md mx-auto">
              Upload a spreadsheet, then ask in plain English — by voice or text.
            </p>
          </section>
        )}

        {/* Step 1: Upload */}
        <DatasetUpload onUploadSuccess={handleUploadSuccess} />

        {/* Step 2: Ask — only after upload */}
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
            <div className="w-10 h-10 border-3 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
            <p className="text-sm text-gray-400">Working on your question…</p>
          </div>
        )}

        {/* Step 3: Results */}
        {hasResults && !isLoading && (
          <section className="flex flex-col gap-6 animate-in">
            <InsightPanel
              insight={insight}
              autoSpeak={settings.speakInsight && !settings.skipInsight}
            />
            <ChartPanel result={result} intent={intent} />
            <ResultTable result={result} />
            <TechnicalDetails
              sql={sql}
              plan={plan}
              metadata={metadata}
              warnings={warnings}
            />
          </section>
        )}
      </main>
    </div>
  );
}
