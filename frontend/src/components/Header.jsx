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

  const status = isProcessing ? 'working' : online ? 'ready' : 'offline';

  return (
    <header className="sticky top-0 z-50 bg-[#030712]/80 backdrop-blur-md border-b border-white/5">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="text-lg">📊</span>
          <span className="font-bold text-white text-sm sm:text-base">Voice BI</span>
        </div>

        <div className={`flex items-center gap-2 text-xs font-medium ${
          status === 'working' ? 'text-amber-400' : status === 'ready' ? 'text-emerald-400' : 'text-red-400'
        }`}>
          <span className={`w-2 h-2 rounded-full ${
            status === 'working' ? 'bg-amber-400 animate-pulse'
              : status === 'ready' ? 'bg-emerald-400' : 'bg-red-400'
          }`} />
          {status === 'working' ? 'Analyzing' : status === 'ready' ? 'Ready' : 'Offline'}
        </div>
      </div>
    </header>
  );
}
