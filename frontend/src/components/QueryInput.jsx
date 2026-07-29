import { useState, useEffect, useCallback } from 'react';
import { getModels, clearCache } from '../services/api';
import { useVoiceInput } from '../hooks/useVoice';
import { TbMicrophone, TbMicrophoneOff, TbSend, TbSettings, TbHistory, TbX, TbSparkles } from 'react-icons/tb';

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
    <section className="relative w-full max-w-3xl mx-auto">
      {businessType && (
        <div className="flex items-center justify-center mb-4 gap-2 text-sm text-zinc-500">
          <TbSparkles className="w-4 h-4 text-[#D97757]" />
          <span>Ask about your <strong className="text-zinc-300 font-medium">{businessType.toLowerCase()}</strong> data</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="relative z-10">
        <div className={`ask-bar flex items-center p-1.5 pl-2 ${isListening ? 'is-listening' : ''}`}>

          <div className="pl-2 pr-1 flex shrink-0">
            {voiceSupported && (
              <button
                type="button"
                onClick={isListening ? stopListening : startListening}
                disabled={isLoading}
                title={isListening ? 'Stop recording' : 'Use voice input'}
                className={`
                  p-2 rounded-full flex items-center justify-center transition-colors
                  ${isListening
                    ? 'bg-red-500/15 text-red-400 animate-pulse'
                    : 'text-zinc-500 hover:text-[#D97757] hover:bg-[#D97757]/10'
                  }
                `}
              >
                {isListening ? <TbMicrophoneOff className="w-5 h-5" /> : <TbMicrophone className="w-5 h-5" />}
              </button>
            )}
          </div>

          <input
            id="query-input"
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder={isListening ? 'Listening...' : 'Ask a question about your data…'}
            disabled={isLoading}
            className="flex-1 w-full bg-transparent text-base text-zinc-100 placeholder:text-zinc-600 outline-none px-2 py-2.5 disabled:opacity-50"
          />

          <div className="pr-1 pl-1 shrink-0">
            <button
              type="submit"
              disabled={!query.trim() || isLoading}
              className="btn-primary w-10 h-10 rounded-full disabled:opacity-40 flex items-center justify-center"
            >
              {isLoading ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              ) : (
                <TbSend className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>
      </form>

      {voiceError && <p className="text-red-400 text-sm mt-3 text-center">{voiceError}</p>}

      {/* Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mt-5 px-2">
        {/* Suggestions */}
        <div className="flex-1 min-w-0 relative">
          {suggestions.length > 0 && (
            <div className="flex items-center gap-2 pb-2 overflow-x-auto scrollbar-none">
              {suggestions.map(s => (
                <button
                  key={s}
                  type="button"
                  onClick={() => { setQuery(s); if (!isLoading) onSubmit(s); }}
                  disabled={isLoading}
                  className="btn-secondary shrink-0 text-xs px-3 py-1.5 rounded-full disabled:opacity-40 whitespace-nowrap"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Secondary Controls */}
        <div className="relative flex items-center gap-1 shrink-0">
          {history.length > 0 && (
            <button
              type="button"
              onClick={() => { setShowHistory(!showHistory); setShowAdvanced(false); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${showHistory ? 'bg-white/10 text-white' : 'text-zinc-500 hover:text-zinc-200 hover:bg-white/5'}`}
            >
              <TbHistory className="w-4 h-4" />
              Recent
            </button>
          )}
          <button
            type="button"
            onClick={() => { setShowAdvanced(!showAdvanced); setShowHistory(false); }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${showAdvanced ? 'bg-white/10 text-white' : 'text-zinc-500 hover:text-zinc-200 hover:bg-white/5'}`}
          >
            <TbSettings className="w-4 h-4" />
            Settings
          </button>

          {/* Popovers — anchored to this row so they open directly under the
              Recent/Settings buttons instead of floating over content below. */}
          {showAdvanced && (
            <div className="absolute right-0 top-full mt-2 w-72 surface-card shadow-2xl p-4 z-30 animate-in">
              <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-4">Analysis Settings</h4>
              <div className="space-y-4">
                <label className="block">
                  <span className="text-sm text-zinc-300 block mb-1.5">AI Model</span>
                  <select
                    value={settings.model || ''}
                    onChange={e => updateSetting('model', e.target.value)}
                    disabled={isLoading}
                    className="w-full bg-[#1C1917] border border-white/10 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none focus:border-[#D97757]/50 transition-colors"
                  >
                    {models.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                </label>

                <div className="space-y-3 pt-2">
                  <Toggle label="Enable Cache (Faster)" checked={settings.cacheMode} onChange={v => updateSetting('cacheMode', v)} disabled={isLoading} />
                  <Toggle label="Fast Mode (Skip Summary)" checked={settings.fastMode} onChange={v => updateSetting('fastMode', v)} disabled={isLoading} />
                  <Toggle label="Voice Answers (Read Aloud)" checked={settings.speakInsight} onChange={v => updateSetting('speakInsight', v)} disabled={isLoading} />
                </div>

                <div className="pt-2 border-t border-white/10 flex justify-end">
                  <button
                    type="button"
                    onClick={handleClearCache}
                    disabled={isLoading}
                    className="text-xs font-medium text-zinc-400 hover:text-[#D97757] transition-colors"
                  >
                    {cacheCleared ? 'Cache Cleared ✓' : 'Clear System Cache'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {showHistory && history.length > 0 && (
            <div className="absolute right-0 top-full mt-2 w-80 surface-card shadow-2xl p-4 z-30 animate-in">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Recent Queries</h4>
                <button onClick={onClearHistory} className="text-[10px] uppercase font-bold text-red-400/80 hover:text-red-400">Clear</button>
              </div>
              <div className="space-y-1 max-h-60 overflow-y-auto pr-1 scrollbar-thin">
                {history.map(item => (
                  <div key={item.id} className="flex items-start gap-2 group p-2 rounded-lg hover:bg-white/5 transition-colors">
                    <button
                      type="button"
                      onClick={() => { setQuery(item.query); if (!isLoading) onSubmit(item.query); setShowHistory(false); }}
                      disabled={isLoading}
                      className="flex-1 text-left text-sm text-zinc-300 hover:text-[#D97757] line-clamp-2 leading-snug"
                    >
                      {item.query}
                    </button>
                    <button
                      type="button"
                      onClick={() => onRemoveHistory?.(item.id)}
                      className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 p-1 rounded transition-all"
                    >
                      <TbX className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Toggle({ label, checked, onChange, disabled }) {
  return (
    <label className="flex items-center justify-between cursor-pointer group">
      <span className="text-sm text-zinc-400 group-hover:text-zinc-300 transition-colors">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative w-10 h-5 rounded-full shrink-0 transition-colors border ${checked ? 'bg-[#D97757] border-[#D97757]' : 'bg-zinc-800 border-zinc-700'} ${disabled ? 'opacity-50' : ''}`}
      >
        <span className={`absolute top-0.5 left-0.5 w-3.5 h-3.5 rounded-full bg-white transition-transform ${checked ? 'translate-x-5' : ''} shadow-sm`} />
      </button>
    </label>
  );
}

export { DEFAULT_SETTINGS };
