import { useEffect, useRef, useState, useCallback } from 'react';
import { sendChatMessage } from '../services/api';
import { useVoiceInput, useSpeechOutput } from '../hooks/useVoice';
import RichText from './RichText';

/**
 * Conversational thread about the dataset, fully voice-capable.
 *
 * - Tap the mic to ask a follow-up by voice (live transcript shown).
 * - Replies are read aloud when speech output is enabled.
 * - Hands-free mode chains the loop: after a reply finishes speaking, the
 *   mic re-opens automatically for the next question — a true "talk to your
 *   data" conversation. Context always reflects the most recent query;
 *   messages are controlled by the parent so the thread survives new queries.
 */
export default function FollowUpChat({
  query, sql, result, insight, model,
  messages, onMessagesChange,
  autoSpeak = false,
}) {
  const [draft, setDraft] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState(null);
  const [handsFree, setHandsFree] = useState(false);
  const scrollRef = useRef(null);
  const handsFreeRef = useRef(false);
  const messagesRef = useRef(messages);
  const startListeningRef = useRef(null);

  useEffect(() => { messagesRef.current = messages; }, [messages]);

  const { speak, stop: stopSpeaking, isSpeaking, isSupported: speechSupported } = useSpeechOutput();

  const submitMessage = useCallback(async (text) => {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;

    const nextMessages = [...messagesRef.current, { role: 'user', content: trimmed }];
    onMessagesChange(nextMessages);
    setDraft('');
    setIsSending(true);
    setError(null);

    try {
      const res = await sendChatMessage(trimmed, {
        query, sql, result, insight, history: messagesRef.current, model,
      });
      if (res.success) {
        onMessagesChange([...nextMessages, { role: 'assistant', content: res.reply }]);
        // Speak the reply if hands-free or auto-speak is on; when hands-free,
        // re-open the mic once speaking finishes to continue the conversation.
        if (handsFreeRef.current || autoSpeak) {
          speak(res.reply, {
            onEnd: () => { if (handsFreeRef.current) startListeningRef.current?.(); },
          });
        }
      } else {
        setError(res.error || 'Could not get a reply.');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSending(false);
    }
  }, [isSending, query, sql, result, insight, model, onMessagesChange, autoSpeak, speak]);

  const { isListening, isSupported: voiceSupported, startListening, stopListening } = useVoiceInput({
    onResult: (transcript) => { setDraft(transcript); submitMessage(transcript); },
    onInterim: (t) => setDraft(t),
    onError: (msg) => { setError(msg); setHandsFree(false); handsFreeRef.current = false; },
  });

  useEffect(() => { startListeningRef.current = startListening; }, [startListening]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const toggleHandsFree = () => {
    const next = !handsFree;
    setHandsFree(next);
    handsFreeRef.current = next;
    if (next) {
      startListening();
    } else {
      stopListening();
      stopSpeaking();
    }
  };

  const handleSend = (e) => {
    e.preventDefault();
    submitMessage(draft);
  };

  if (!result?.rows?.length) return null;

  const status = isListening ? 'Listening…' : isSpeaking ? 'Speaking…' : isSending ? 'Thinking…' : null;

  return (
    <div className="panel-card">
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h3 className="text-xs font-data uppercase tracking-wide text-gray-500">Ask a follow-up</h3>
        <div className="flex items-center gap-3">
          {voiceSupported && speechSupported && (
            <button
              type="button"
              onClick={toggleHandsFree}
              className={`px-2.5 py-1 text-xs font-medium transition-colors flex items-center gap-1.5 ${
                handsFree ? 'bg-[#c8ff4d] text-[#0a0a08]' : 'text-gray-300 hover:text-white bg-white/10 border border-white/10'
              }`}
              title="Hands-free conversation: speak, hear the answer, then keep talking"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${handsFree ? 'bg-[#0a0a08] animate-pulse' : 'bg-gray-500'}`} />
              Hands-free
            </button>
          )}
          {messages.length > 0 && (
            <button
              type="button"
              onClick={() => onMessagesChange([])}
              className="text-xs text-gray-400 hover:text-red-400 transition-colors font-data"
            >
              Clear thread
            </button>
          )}
        </div>
      </div>

      {messages.length > 0 && (
        <div ref={scrollRef} className="space-y-3 mb-4 max-h-72 overflow-y-auto pr-1">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] px-3 py-2 text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-[#c8ff4d] text-[#0a0a08] font-medium'
                    : 'bg-black/30 border border-white/10 text-gray-200'
                }`}
              >
                {m.role === 'user' ? m.content : <RichText text={m.content} />}
              </div>
            </div>
          ))}
          {isSending && (
            <div className="flex justify-start">
              <div className="bg-black/30 border border-white/10 px-3 py-2 text-sm text-gray-500">
                Thinking…
              </div>
            </div>
          )}
        </div>
      )}

      <form onSubmit={handleSend} className="flex gap-2">
        <div className="flex-1 flex items-center gap-2 bg-white/[0.03] border border-white/10 px-3 py-2.5 focus-within:border-[#c8ff4d]/50 transition-colors">
          <input
            type="text"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            placeholder={isListening ? 'Listening…' : 'e.g. "How can I improve my sales with this data?"'}
            disabled={isSending}
            className="flex-1 bg-transparent text-sm text-white placeholder:text-gray-600 outline-none disabled:opacity-50"
          />
          {voiceSupported && (
            <button
              type="button"
              onClick={isListening ? stopListening : startListening}
              disabled={isSending}
              title={isListening ? 'Stop' : 'Speak your question'}
              className={`w-7 h-7 flex items-center justify-center shrink-0 transition-colors ${
                isListening ? 'text-red-400' : 'text-gray-500 hover:text-[#c8ff4d]'
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
          disabled={!draft.trim() || isSending}
          className="btn-primary px-4 py-2.5 text-sm disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
        >
          {isSending ? '…' : 'Send'}
        </button>
      </form>

      {status && <p className="text-[#c8ff4d] text-xs mt-2 font-data">{status}</p>}
      {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
    </div>
  );
}
