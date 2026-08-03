import React from 'react';
import BIChartPanel from './BIChartPanel';

export default function DashboardGrid({ results }) {
  if (!results || results.length === 0) return null;

  return (
    <div className="w-full space-y-6">
      <h2 className="text-2xl font-semibold text-zinc-100 tracking-tight px-2">Generated Dashboard</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 w-full">
        {results.map((res, i) => (
          <div key={i} className="surface-card flex flex-col h-full rounded-2xl overflow-hidden border border-black/5 shadow-sm bg-white/40 backdrop-blur-md transition-all hover:shadow-md">
             <div className="px-5 py-4 border-b border-black/5 bg-black/[0.02]">
                <h3 className="text-sm font-medium text-zinc-100 capitalize">{res.query}</h3>
             </div>
             <div className="p-4 flex-1 min-h-[400px]">
                {res.success ? (
                   <BIChartPanel result={res.result} intent={res.metadata?.plan?.intent} query={res.query} />
                ) : (
                   <div className="text-[#9C4A2A] text-sm p-4 bg-[#9C4A2A]/10 rounded-lg h-full flex items-center justify-center text-center">
                     {res.error || "Failed to generate chart"}
                   </div>
                )}
             </div>
          </div>
        ))}
      </div>
    </div>
  );
}
