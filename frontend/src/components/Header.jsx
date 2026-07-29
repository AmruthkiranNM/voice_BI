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
  const dotClass = status === 'working' ? 'bg-[#D97757] animate-pulse' : status === 'ready' ? 'bg-emerald-500' : 'bg-red-500';
  const label = status === 'working' ? 'Processing' : status === 'ready' ? 'Local · Private' : 'Offline';
  const textClass = status === 'working' ? 'text-[#D97757]' : status === 'ready' ? 'text-zinc-500' : 'text-red-400';

  return (
    <div className="flex items-center gap-2 px-1">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotClass}`} />
      <span className={`text-xs font-medium ${textClass}`}>{label}</span>
    </div>
  );
}
