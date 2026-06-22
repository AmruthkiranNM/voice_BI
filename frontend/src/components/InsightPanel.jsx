import { useEffect } from 'react';
import { useSpeechOutput } from '../hooks/useVoice';

export default function InsightPanel({ insight, autoSpeak = false }) {
  const { speak, stop, isSpeaking, isSupported } = useSpeechOutput();

  useEffect(() => {
    if (autoSpeak && insight) speak(insight);
    return () => stop();
  }, [insight, autoSpeak]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!insight) return null;

  return (
    <div className="panel-card w-full bg-gradient-to-br from-gray-900 to-indigo-950/20 border-indigo-500/20">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-400">💡</div>
          <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider">Business Analysis</h3>
        </div>

        {isSupported && (
          <button
            type="button"
            onClick={() => isSpeaking ? stop() : speak(insight)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold
                       bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 hover:bg-indigo-500/20 transition-colors"
          >
            {isSpeaking ? (
              <><span className="w-2 h-2 rounded-full bg-red-400 animate-pulse" /> Stop</>
            ) : (
              <>🔊 Listen</>
            )}
          </button>
        )}
      </div>

      <p className="text-base text-gray-300 leading-relaxed font-medium">
        {highlightNumbers(insight)}
      </p>
    </div>
  );
}

function highlightNumbers(text) {
  const parts = text.split(/(\$?[\d,]+\.?\d*%?)/g);
  return parts.map((part, i) =>
    /^\$?[\d,]+\.?\d*%?$/.test(part)
      ? <span key={i} className="font-bold text-amber-400 bg-amber-500/10 px-1 rounded mx-0.5">{part}</span>
      : part
  );
}
