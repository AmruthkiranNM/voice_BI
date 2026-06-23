import { useState, useEffect } from 'react';
import { checkHealth } from '../services/api';

export default function Header({ isProcessing, wide = false }) {
  const [online, setOnline] = useState(false);

  useEffect(() => {
    const check = () => checkHealth().then(d => setOnline(d.status === 'healthy'));
    check();
    const id = setInterval(check, 15000);
    return () => clearInterval(id);
  }, []);

  const status = isProcessing ? 'working' : online ? 'ready' : 'offline';

  return (
    <header className="sticky top-0 z-50 bg-[#0a0a08]/90 backdrop-blur-sm border-b border-white/8">
      <div className={`${wide ? 'max-w-[1600px]' : 'max-w-3xl'} mx-auto px-4 sm:px-6 lg:px-10 h-14 flex items-center justify-between`}>
        <div className="flex items-center gap-2.5">
          <svg width="22" height="22" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <rect width="32" height="32" rx="6" fill="#c8ff4d" />
            <path d="M7 22V14M14 22V8M21 22V12M25 22V16" stroke="#0a0a08" strokeWidth="3" strokeLinecap="round" />
          </svg>
          <span className="font-semibold text-white text-sm sm:text-base tracking-tight" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Voice BI
          </span>
        </div>

        <div className={`flex items-center gap-2 text-xs font-medium font-data uppercase tracking-wide ${
          status === 'working' ? 'text-amber-400' : status === 'ready' ? 'text-[#c8ff4d]' : 'text-red-400'
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${
            status === 'working' ? 'bg-amber-400 animate-pulse'
              : status === 'ready' ? 'bg-[#c8ff4d]' : 'bg-red-400'
          }`} />
          {status === 'working' ? 'Analyzing' : status === 'ready' ? 'Ready' : 'Offline'}
        </div>
      </div>
    </header>
  );
}
