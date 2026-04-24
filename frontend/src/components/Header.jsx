/**
 * Header — Top bar with project title, API mode selector, and status
 */
import { useState, useEffect } from 'react';
import { checkHealth } from '../services/api';

export default function Header({ isProcessing }) {
  const [online, setOnline] = useState(false);

  useEffect(() => {
    const check = () => checkHealth().then(d => setOnline(d.status === 'healthy'));
    check();
    const id = setInterval(check, 15000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="sticky top-0 z-50 bg-card/90 backdrop-blur-md border-b border-border">
      {/* Accent line */}
      <div className="h-[2px] bg-gradient-to-r from-indigo via-indigo-light to-green" />

      <div className="max-w-7xl mx-auto px-8 h-16 flex items-center justify-between">
        {/* Left — Title */}
        <div className="flex items-center gap-4">
          <div className="w-9 h-9 rounded-xl bg-indigo/10 border border-indigo/20 flex items-center justify-center text-lg">
            🧠
          </div>
          <div>
            <h1 className="text-base font-bold text-text-primary leading-tight">
              Agentic AI BI System
            </h1>
            <p className="text-[11px] text-text-muted">
              RAG-Powered Business Intelligence
            </p>
          </div>
        </div>

        {/* Right — Controls */}
        <div className="flex items-center gap-4">

          {/* Status Badge */}
          <div className={`flex items-center gap-2 px-4 py-2 rounded-xl border text-xs font-semibold
            ${isProcessing
              ? 'bg-amber/10 border-amber/30 text-amber'
              : online
                ? 'bg-green/10 border-green/30 text-green'
                : 'bg-red/10 border-red/30 text-red'
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${
              isProcessing ? 'bg-amber animate-pulse' : online ? 'bg-green' : 'bg-red'
            }`} />
            {isProcessing ? 'Processing...' : online ? 'Online' : 'Offline'}
          </div>
        </div>
      </div>
    </header>
  );
}
