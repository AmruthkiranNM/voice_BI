import { useState, useRef, useEffect } from 'react';
import { sendChatMessage } from '../services/api';
import { TbMessageCircle, TbSend, TbRobot, TbUser, TbMicrophone, TbAlertCircle } from 'react-icons/tb';
import { useVoiceInput } from '../hooks/useVoice';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function FollowUpChat({
  query, sql, result, insight, model, tableName, tableNames,
  messages, onMessagesChange, autoSpeak, pendingQuestion, onPendingQuestionHandled,
}) {
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef(null);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  const { isListening, isSupported, startListening, stopListening } = useVoiceInput({
    onResult: (t) => { setInput(t); handleSend(t); },
    onInterim: setInput,
  });

  // A table row or chart bar was clicked elsewhere on the dashboard — ask
  // about it here instead of duplicating the chat/send logic at that call site.
  useEffect(() => {
    if (!pendingQuestion) return;
    handleSend(pendingQuestion);
    onPendingQuestionHandled?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingQuestion]);

  const handleSend = async (overrideInput = null) => {
    const text = (overrideInput || input).trim();
    if (!text) return;

    setInput('');
    const newMsgs = [...messages, { role: 'user', content: text }];
    onMessagesChange(newMsgs);
    setIsTyping(true);

    try {
      const response = await sendChatMessage(text, {
        query,
        sql,
        result,
        insight: insight || result?.insight,
        history: newMsgs.slice(-5),
        model,
        tableName,
        tableNames,
      });

      const aiMsg = { role: 'assistant', content: response.reply };
      onMessagesChange([...newMsgs, aiMsg]);

      // Speak AI response if autoSpeak is enabled
      if (autoSpeak && window.speechSynthesis) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(response.reply);
        utterance.rate = 1.05;
        window.speechSynthesis.speak(utterance);
      }
    } catch (err) {
      onMessagesChange([...newMsgs, { role: 'assistant', content: 'Sorry, I encountered an error: ' + err.message, isError: true }]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className="panel-card flex flex-col h-[500px] border-t-4 border-t-violet-500 shadow-xl shadow-violet-500/5 relative overflow-hidden">
      <div className="absolute top-0 right-0 w-64 h-64 bg-violet-500/5 rounded-full blur-3xl pointer-events-none"></div>
      
      <div className="flex items-center gap-3 mb-4 pb-4 border-b border-black/5 relative z-10">
        <div className="p-2 bg-violet-500/10 rounded-lg border border-violet-500/20">
          <TbMessageCircle className="w-5 h-5 text-violet-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-zinc-100 tracking-wide">AI Data Analyst</h3>
          <p className="text-xs text-zinc-500">Ask follow-up questions about this result</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto mb-4 space-y-4 pr-2 scrollbar-thin relative z-10" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-zinc-500 space-y-3">
            <TbRobot className="w-10 h-10 opacity-20" />
            <p className="text-sm text-center max-w-xs">I understand the data shown above. Ask me to clarify, summarize, or extract deeper insights.</p>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 border shadow-sm
                ${msg.role === 'user' ? 'bg-blue-600/20 border-blue-500/30' : msg.isError ? 'bg-red-500/20 border-red-500/30' : 'bg-violet-600/20 border-violet-500/30'}
              `}>
                {msg.role === 'user' ? <TbUser className="w-4 h-4 text-blue-400" /> : msg.isError ? <TbAlertCircle className="w-4 h-4 text-red-400" /> : <TbRobot className="w-4 h-4 text-violet-400" />}
              </div>
              <div className={`px-4 py-3 rounded-2xl max-w-[85%] text-[13px] leading-relaxed shadow-sm
                ${msg.role === 'user'
                  ? 'bg-blue-600/10 border border-blue-500/20 text-zinc-200 rounded-tr-sm'
                  : msg.isError
                    ? 'bg-red-500/10 border border-red-500/20 text-red-300 rounded-tl-sm font-light'
                    : 'bg-black/[0.03] border border-black/5 text-zinc-300 rounded-tl-sm font-light'}
              `}>
                {msg.role === 'user' ? (
                  msg.content
                ) : (
                  <div className="prose prose-invert prose-sm max-w-none prose-p:leading-relaxed prose-pre:bg-black/40 prose-pre:border prose-pre:border-black/10">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        
        {isTyping && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-violet-600/20 border border-violet-500/30 flex items-center justify-center shrink-0">
              <TbRobot className="w-4 h-4 text-violet-400" />
            </div>
            <div className="px-4 py-3 rounded-2xl bg-black/[0.03] border border-black/5 rounded-tl-sm flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 bg-violet-400/50 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1.5 h-1.5 bg-violet-400/50 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1.5 h-1.5 bg-violet-400/50 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
      </div>

      <div className="relative group z-10">
        <div className="absolute -inset-0.5 bg-gradient-to-r from-violet-500/20 to-blue-500/20 rounded-xl blur opacity-0 group-focus-within:opacity-100 transition-opacity"></div>
        <div className="relative flex items-center bg-bg border border-black/10 rounded-xl focus-within:border-violet-500/50 overflow-hidden shadow-inner">
          {isSupported && (
            <button
              onClick={isListening ? stopListening : startListening}
              className={`p-3 transition-colors ${isListening ? 'text-red-400 bg-red-400/10' : 'text-zinc-500 hover:text-violet-400 hover:bg-violet-400/10'}`}
            >
              <TbMicrophone className="w-5 h-5" />
            </button>
          )}
          
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSend()}
            placeholder={isListening ? 'Listening...' : 'Ask a follow-up question...'}
            className="flex-1 bg-transparent text-sm text-zinc-100 px-3 py-4 outline-none placeholder:text-zinc-600"
            disabled={isTyping}
          />
          
          <button
            onClick={() => handleSend()}
            disabled={!input.trim() || isTyping}
            className="p-3 mr-1 my-1 rounded-lg bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-30 transition-colors shadow-sm"
          >
            <TbSend className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
