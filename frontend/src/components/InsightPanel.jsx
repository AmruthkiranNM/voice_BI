import { useEffect } from 'react';
import { useSpeechOutput } from '../hooks/useVoice';

export default function InsightPanel({ insight, autoSpeak = false }) {
  const { speak, stop, isSpeaking, isSupported } = useSpeechOutput();

  useEffect(() => {
    if (autoSpeak && insight) speak(insight);
    return () => stop();
  }, [insight, autoSpeak, speak, stop]);

  if (!insight) return null;

  return (
    <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-5 sm:p-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">Answer</h3>
        {isSupported && (
          <button
            type="button"
            onClick={() => isSpeaking ? stop() : speak(insight)}
            className="text-xs text-gray-500 hover:text-indigo-400 transition-colors"
          >
            {isSpeaking ? 'Stop' : '🔊 Listen'}
          </button>
        )}
      </div>
      <p className="text-sm sm:text-base text-gray-300 leading-relaxed">
        {highlightNumbers(insight)}
      </p>
    </div>
  );
}

function highlightNumbers(text) {
  const parts = text.split(/(\$?[\d,]+\.?\d*%?)/g);
  return parts.map((part, i) =>
    /^\$?[\d,]+\.?\d*%?$/.test(part)
      ? <span key={i} className="font-semibold text-amber-300">{part}</span>
      : part
  );
}
