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
  suggestions = [],
  businessType,
  history = [],
  onClearHistory,
  onRemoveHistory,
}) {
  const [query, setQuery] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [models, setModels] = useState([]);
  const [cacheCleared, setCacheCleared] = useState(false);
  const [voiceError, setVoiceError] = useState(null);

  const handleVoiceResult = useCallback((transcript) => {
    setVoiceError(null);
    setQuery(transcript);
    if (!isLoading) onSubmit(transcript);
  }, [isLoading, onSubmit]);

  const { isListening, isSupported: voiceSupported, startListening, stopListening } = useVoiceInput({
    onResult: handleVoiceResult,
    onInterim: (t) => setQuery(t),
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

  return (
    <section className="space-y-4">
      {businessType && (
        <p className="text-sm text-gray-400">
          Ask anything about your <span className="text-white font-medium">{businessType.toLowerCase()}</span>
        </p>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="flex-1 flex items-center gap-2 bg-white/[0.03] border border-white/10 px-4 py-3 focus-within:border-[#c8ff4d]/50 transition-colors">
          <input
            id="query-input"
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder='e.g. "What were my top selling products last month?"'
            disabled={isLoading}
            className="flex-1 bg-transparent text-sm sm:text-base text-white placeholder:text-gray-600 outline-none disabled:opacity-50"
          />

          {voiceSupported && (
            <button
              type="button"
              onClick={isListening ? stopListening : startListening}
              disabled={isLoading}
              title={isListening ? 'Stop' : 'Speak'}
              className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors ${
                isListening
                  ? 'bg-red-500/20 text-red-400'
                  : 'text-gray-500 hover:text-[#c8ff4d]'
              }`}
            >
              {isListening ? (
                <span className="w-2.5 h-2.5 rounded-full bg-red-400 animate-pulse" />
              ) : (
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.71V21h2v-3.29A7 7 0 0 0 19 11h-2Z" />
                </svg>
              )}
            </button>
          )}
        </div>

        <button
          type="submit"
          disabled={!query.trim() || isLoading}
          className="btn-primary px-5 py-3 text-sm disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
        >
          {isLoading ? '…' : 'Ask'}
        </button>
      </form>

      {voiceError && <p className="text-red-400 text-xs">{voiceError}</p>}
      {isListening && (
        <p className="text-[#c8ff4d] text-xs animate-pulse">Listening…</p>
      )}

      {suggestions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500">Try asking:</p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map(s => (
              <button
                key={s}
                type="button"
                onClick={() => { setQuery(s); if (!isLoading) onSubmit(s); }}
                disabled={isLoading}
                className="text-left text-xs sm:text-sm text-gray-300 px-3 py-2 bg-white/[0.03] border border-white/10
                           hover:border-[#c8ff4d]/40 hover:text-white disabled:opacity-40 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center gap-4 pt-1">
        <button
          type="button"
          onClick={() => setShowAdvanced(v => !v)}
          className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
        >
          {showAdvanced ? 'Hide settings' : 'Settings'}
        </button>
        {history.length > 0 && (
          <button
            type="button"
            onClick={() => setShowHistory(v => !v)}
            className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
          >
            {showHistory ? 'Hide recent' : `Recent (${history.length})`}
          </button>
        )}
      </div>

      {showAdvanced && (
        <div className="p-4 bg-black/20 border border-white/10 space-y-4 text-sm">
          <label className="block">
            <span className="text-xs text-gray-500 block mb-1">AI model</span>
            <select
              value={settings.model || ''}
              onChange={e => updateSetting('model', e.target.value)}
              disabled={isLoading}
              className="w-full bg-gray-900 border border-white/10 px-3 py-2 text-sm text-gray-200 outline-none font-data"
            >
              {models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <Toggle label="Remember answers (cache)" checked={settings.cacheMode}
            onChange={v => updateSetting('cacheMode', v)} disabled={isLoading} />
          <Toggle label="Fast mode (skip summary)" checked={settings.fastMode}
            onChange={v => updateSetting('fastMode', v)} disabled={isLoading} />
          <Toggle label="Read answers aloud" checked={settings.speakInsight}
            onChange={v => updateSetting('speakInsight', v)} disabled={isLoading} />
          <button type="button" onClick={handleClearCache} disabled={isLoading}
            className="text-xs text-gray-500 hover:text-amber-400">
            {cacheCleared ? 'Cache cleared' : 'Clear cache'}
          </button>
        </div>
      )}

      {showHistory && history.length > 0 && (
        <div className="space-y-1">
          {history.map(item => (
            <div key={item.id} className="flex items-center gap-2 group">
              <button
                type="button"
                onClick={() => { setQuery(item.query); if (!isLoading) onSubmit(item.query); }}
                disabled={isLoading}
                className="flex-1 text-left text-xs text-gray-500 hover:text-[#c8ff4d] truncate py-1.5"
              >
                {item.query}
              </button>
              <button type="button" onClick={() => onRemoveHistory?.(item.id)}
                className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 text-xs px-1">
                ×
              </button>
            </div>
          ))}
          <button type="button" onClick={onClearHistory}
            className="text-xs text-gray-600 hover:text-red-400 pt-1">
            Clear all
          </button>
        </div>
      )}
    </section>
  );
}

function Toggle({ label, checked, onChange, disabled }) {
  return (
    <label className="flex items-center gap-3 cursor-pointer">
      <button type="button" role="switch" aria-checked={checked} disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative w-9 h-5 rounded-full shrink-0 transition-colors ${checked ? 'bg-[#c8ff4d]' : 'bg-gray-700'} ${disabled ? 'opacity-30' : ''}`}>
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-[#0a0a08] transition-transform ${checked ? 'translate-x-4' : ''}`} />
      </button>
      <span className="text-xs text-gray-400">{label}</span>
    </label>
  );
}

export { DEFAULT_SETTINGS };
