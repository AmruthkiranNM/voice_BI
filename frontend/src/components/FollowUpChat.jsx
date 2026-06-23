import { useEffect, useRef, useState } from 'react';
import { sendChatMessage } from '../services/api';

/**
 * Conversational thread about the dataset. Context (query/sql/result/insight)
 * always reflects the most recent query, but `messages`/`onMessagesChange`
 * are controlled by the parent so the conversation persists across multiple
 * top-level questions in the same session — only a new dataset upload
 * clears it.
 */
export default function FollowUpChat({ query, sql, result, insight, model, messages, onMessagesChange }) {
  const [draft, setDraft] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || isSending) return;

    const nextMessages = [...messages, { role: 'user', content: text }];
    onMessagesChange(nextMessages);
    setDraft('');
    setIsSending(true);
    setError(null);

    try {
      const res = await sendChatMessage(text, { query, sql, result, insight, history: messages, model });
      if (res.success) {
        onMessagesChange([...nextMessages, { role: 'assistant', content: res.reply }]);
      } else {
        setError(res.error || 'Could not get a reply.');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSending(false);
    }
  };

  if (!result?.rows?.length) return null;

  return (
    <div className="panel-card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-data uppercase tracking-wide text-gray-500">Ask a follow-up</h3>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={() => onMessagesChange([])}
            className="text-xs text-gray-600 hover:text-red-400 transition-colors font-data"
          >
            Clear thread
          </button>
        )}
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
                {m.content}
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
        <input
          type="text"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          placeholder='e.g. "How can I improve my sales with this data?"'
          disabled={isSending}
          className="flex-1 bg-white/[0.03] border border-white/10 px-3 py-2.5 text-sm text-white placeholder:text-gray-600 outline-none focus:border-[#c8ff4d]/50 transition-colors disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!draft.trim() || isSending}
          className="btn-primary px-4 py-2.5 text-sm disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
        >
          {isSending ? '…' : 'Send'}
        </button>
      </form>

      {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
    </div>
  );
}
