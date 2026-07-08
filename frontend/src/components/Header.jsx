import { useState, useEffect } from 'react';
import { checkHealth } from '../services/api';
import { TbCloudCheck, TbCloudOff, TbCloudUpload } from 'react-icons/tb';

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
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.02] border border-white/5">
      {status === 'working' ? (
        <TbCloudUpload className="w-4 h-4 text-blue-400 animate-pulse" />
      ) : status === 'ready' ? (
        <TbCloudCheck className="w-4 h-4 text-emerald-400" />
      ) : (
        <TbCloudOff className="w-4 h-4 text-red-400" />
      )}
      <span className={`text-[11px] font-medium uppercase tracking-wider ${
        status === 'working' ? 'text-blue-400' : status === 'ready' ? 'text-emerald-400' : 'text-red-400'
      }`}>
        {status === 'working' ? 'Processing' : status === 'ready' ? 'Connected' : 'Offline'}
      </span>
    </div>
  );
}
