import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { getRandomMessage } from '../utils/complexityAnalyzer';

export default function ActivityConsole({ isActive, backendFinished }) {
  const [messages, setMessages] = useState([]);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!isActive) return;

    // Add a new message every 1-3 seconds
    const interval = setInterval(() => {
      setMessages(prev => {
        const newMsg = {
          id: Date.now(),
          text: backendFinished ? "Awaiting final visualization render..." : getRandomMessage(),
          time: new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 2 })
        };
        const next = [...prev, newMsg];
        if (next.length > 8) return next.slice(next.length - 8);
        return next;
      });
    }, Math.random() * 2000 + 1000);

    return () => clearInterval(interval);
  }, [isActive, backendFinished]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div className="flex flex-col h-full bg-zinc-950/80 rounded-xl border border-zinc-800/80 overflow-hidden font-mono text-xs shadow-inner">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800/80 bg-zinc-900/50">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500/80"></div>
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80"></div>
          <div className="w-2.5 h-2.5 rounded-full bg-green-500/80"></div>
        </div>
        <span className="text-zinc-500 text-[10px] uppercase ml-2 tracking-wider">AI Execution Log</span>
      </div>
      
      <div 
        ref={containerRef}
        className="flex-1 p-3 overflow-y-auto space-y-1.5 text-zinc-400 scrollbar-thin scrollbar-thumb-zinc-800"
      >
        <AnimatePresence>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-start gap-2"
            >
              <span className="text-zinc-600 shrink-0">[{msg.time}]</span>
              <span className="text-emerald-400/80">{'>'}</span>
              <span className="text-zinc-300 break-words">{msg.text}</span>
            </motion.div>
          ))}
        </AnimatePresence>
        
        {isActive && (
          <motion.div 
            animate={{ opacity: [1, 0] }}
            transition={{ repeat: Infinity, duration: 0.8 }}
            className="inline-block w-2 h-3 bg-zinc-400 ml-1 mt-1"
          />
        )}
      </div>
    </div>
  );
}
