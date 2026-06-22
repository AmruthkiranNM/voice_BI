import { useState, useEffect, useCallback } from 'react';
import { getModels, clearCache } from '../services/api';
import { useVoiceInput } from '../hooks/useVoice';

const DEFAULT_SETTINGS = {
  model: '',
  cacheMode: true,
  fastMode: false,
  skipInsight: false,
  speakInsight: true,
};

export default function QueryInput({
  onSubmit,
  isLoading,
  settings,
  onSettingsChange,
  hasDataset,
  suggestions = [],
  history = [],
  onClearHistory,
  onRemoveHistory,
}) {
  const [query, setQuery] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [models, setModels] = useState([]);
  const [cacheCleared, setCacheCleared] = useState(false);
  const [voiceError, setVoiceError] = useState(null);

  const handleVoiceResult = useCallback((transcript) => {
    setVoiceError(null);
    setQuery(transcript);
    if (!isLoading && hasDataset) onSubmit(transcript);
  }, [isLoading, hasDataset, onSubmit]);

  const { isListening, isSupported: voiceSupported, startListening, stopListening } = useVoiceInput({
    onResult: handleVoiceResult,
    onError: setVoiceError,
  });

  useEffect(() => {
    getModels().then(list => {
      setModels(list);
      if (list.length > 0 && !settings.model) {
        onSettingsChange({ ...settings, model: list[0] });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!hasDataset) return;
    if (query.trim() && !isLoading) onSubmit(query.trim());
  };

  const updateSetting = (key, value) => {
    const next = { ...settings, [key]: value };
    if (key === 'fastMode' && value) next.skipInsight = true;
    onSettingsChange(next);
  };

  const handleClearCache = async () => {
    await clearCache();
    setCacheCleared(true);
    setTimeout(() => setCacheCleared(false), 2000);
  };

  const displaySuggestions = suggestions.length > 0 ? suggestions : [];

  return (
    <div className="fade-up">
      <div className="flex items-center gap-2 mb-3 px-1">
        <span className="text-[10px] font-bold uppercase tracking-widest text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded">Step 2</span>
        <span className="text-sm font-semibold text-gray-300">Ask About Your Data</span>
        {!hasDataset && (
          <span className="text-xs text-amber-400 ml-auto">Upload a CSV first</span>
        )}
      </div>

      <form
        onSubmit={handleSubmit}
        className={`bg-card border rounded-2xl p-5 flex gap-3 items-center transition-colors duration-200
          ${hasDataset ? 'border-border hover:border-border-hover' : 'border-amber-500/30 opacity-80'}`}
      >
        <svg className="w-5 h-5 text-text-muted flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>

        <input
          id="query-input"
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder={hasDataset
            ? 'Type or speak your question — e.g. "What were my top selling products?"'
            : 'Upload your CSV above, then ask a question here...'}
          disabled={isLoading || !hasDataset}
          className="flex-1 bg-transparent text-base text-text-primary placeholder:text-text-muted outline-none disabled:opacity-50"
        />

        {voiceSupported && (
          <button
            type="button"
            onClick={isListening ? stopListening : startListening}
            disabled={isLoading || !hasDataset}
            title={isListening ? 'Stop listening' : 'Ask with your voice'}
            className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all flex-shrink-0
              ${isListening
                ? 'bg-red-500/20 border-2 border-red-500 text-red-400 animate-pulse'
                : 'bg-gray-800 border border-gray-700 text-gray-400 hover:text-indigo-400 hover:border-indigo-500/50'}
              disabled:opacity-30 disabled:cursor-not-allowed`}
          >
            {isListening ? (
              <span className="w-3 h-3 rounded-full bg-red-500" />
            ) : (
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.71V21h2v-3.29A7 7 0 0 0 19 11h-2Z" />
              </svg>
            )}
          </button>
        )}

        <button
          id="submit-btn"
          type="submit"
          disabled={!query.trim() || isLoading || !hasDataset}
          className="px-6 py-2.5 rounded-xl text-sm font-bold text-white bg-indigo hover:bg-indigo-light
                     disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 whitespace-nowrap"
        >
          {isLoading ? 'Analyzing...' : 'Analyze'}
        </button>
      </form>

      {voiceError && (
        <p className="text-amber-400 text-xs mt-2 px-2">{voiceError}</p>
      )}
      {isListening && (
        <p className="text-indigo-400 text-xs mt-2 px-2 animate-pulse">Listening... speak your business question</p>
      )}

      {/* Advanced Settings */}
      <div className="mt-3">
        <button
          type="button"
          onClick={() => setShowAdvanced(v => !v)}
          className="flex items-center gap-2 text-xs font-semibold text-text-muted hover:text-indigo transition-colors px-2"
        >
          <svg className={`w-3.5 h-3.5 transition-transform ${showAdvanced ? 'rotate-90' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m9 5 7 7-7 7" />
          </svg>
          Advanced Settings
        </button>

        {showAdvanced && (
          <div className="mt-3 p-4 rounded-xl bg-card border border-border grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">Ollama Model</span>
              <select
                value={settings.model || ''}
                onChange={e => updateSetting('model', e.target.value)}
                disabled={isLoading}
                className="bg-bg border border-border rounded-lg px-3 py-2 text-sm text-emerald-400 font-medium outline-none"
              >
                {models.length === 0
                  ? <option value="">Loading...</option>
                  : models.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>

            <Toggle label="Cache Mode" description="Instant results for repeated questions"
              checked={settings.cacheMode} onChange={v => updateSetting('cacheMode', v)} disabled={isLoading} />

            <Toggle label="Fast Mode" description="Skip planner for quicker analysis"
              checked={settings.fastMode} onChange={v => updateSetting('fastMode', v)} disabled={isLoading} />

            <Toggle label="Speak Insights" description="Read AI analysis aloud when ready"
              checked={settings.speakInsight} onChange={v => updateSetting('speakInsight', v)} disabled={isLoading} />

            <div className="sm:col-span-2 flex justify-end pt-1 border-t border-border">
              <button type="button" onClick={handleClearCache} disabled={isLoading}
                className="text-xs font-semibold text-text-muted hover:text-amber transition-colors">
                {cacheCleared ? 'Cache cleared!' : 'Clear cache'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Query history */}
      {history.length > 0 && (
        <div className="mt-4 px-2">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] text-text-muted font-medium">Recent questions</span>
            <button type="button" onClick={onClearHistory}
              className="text-[10px] text-text-muted hover:text-red-400 transition-colors">
              Clear all
            </button>
          </div>
          <div className="flex flex-col gap-1.5 max-h-36 overflow-y-auto">
            {history.map(item => (
              <div key={item.id}
                className="flex items-center gap-2 group rounded-lg hover:bg-gray-800/40 px-2 py-1.5">
                <button
                  type="button"
                  onClick={() => { setQuery(item.query); if (!isLoading && hasDataset) onSubmit(item.query); }}
                  disabled={isLoading || !hasDataset}
                  className="flex-1 text-left text-xs text-text-secondary hover:text-indigo truncate disabled:opacity-40"
                >
                  {item.query}
                  {item.rowCount != null && (
                    <span className="text-gray-600 ml-2">{item.rowCount} rows</span>
                  )}
                </button>
                <button type="button" onClick={() => onRemoveHistory?.(item.id)}
                  className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 text-xs px-1">
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Dynamic suggestions from uploaded data */}
      {hasDataset && displaySuggestions.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-4 px-2">
          <span className="text-[11px] text-text-muted self-center mr-1 font-medium">Suggested for your data:</span>
          {displaySuggestions.map(s => (
            <button
              key={s}
              onClick={() => { setQuery(s); if (!isLoading) onSubmit(s); }}
              disabled={isLoading}
              className="px-3 py-1.5 rounded-lg text-xs text-text-secondary bg-card border border-border
                         hover:text-indigo hover:border-indigo/40 disabled:opacity-30 transition-all"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Toggle({ label, description, checked, onChange, disabled }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer select-none">
      <button type="button" role="switch" aria-checked={checked} disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative w-10 h-5 rounded-full flex-shrink-0 mt-0.5 transition-colors
          ${checked ? 'bg-indigo' : 'bg-gray-700'} ${disabled ? 'opacity-40' : ''}`}>
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform
          ${checked ? 'translate-x-5' : ''}`} />
      </button>
      <div>
        <span className="text-sm font-semibold text-text-primary">{label}</span>
        <p className="text-[11px] text-text-muted mt-0.5">{description}</p>
      </div>
    </label>
  );
}

export { DEFAULT_SETTINGS };
