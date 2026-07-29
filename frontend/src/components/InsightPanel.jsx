import { useEffect } from 'react';
import { useSpeechOutput } from '../hooks/useVoice';
import RichText from './RichText';

export default function InsightPanel({ insight, autoSpeak = false }) {
  const { speak, stop, isSpeaking, isSupported } = useSpeechOutput();

  useEffect(() => {
    if (autoSpeak && insight) speak(insight);
    return () => stop();
  }, [insight, autoSpeak, speak, stop]);

  if (!insight) return null;

  return (
    <div className="panel-card">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-data uppercase tracking-wide text-gray-500">Answer</h3>
        {isSupported && (
          <button
            type="button"
            onClick={() => isSpeaking ? stop() : speak(insight)}
            className="text-xs text-gray-500 hover:text-[#9C4A2A] transition-colors"
          >
            {isSpeaking ? 'Stop' : 'Listen'}
          </button>
        )}
      </div>
      <RichText text={insight} className="text-sm sm:text-base text-[#3D3226]" />
    </div>
  );
}
