import { useState } from 'react';
import {
  TbDatabaseImport, TbLayoutDashboard,
  TbDatabase, TbFileSpreadsheet, TbTrash, TbLoader2,
} from 'react-icons/tb';
import { deleteSource } from '../services/api';
import Header from './Header';

export default function Sidebar({
  currentView,
  onViewChange,
  isMobileOpen,
  setIsMobileOpen,
  sources = [],
  activeSourceId,
  onSelectSource,
  onDatasetsChanged,
  isProcessing,
}) {
  const [removingId, setRemovingId] = useState(null);

  const navItems = [
    { id: 'dashboard', label: 'Analysis Workspace', icon: TbLayoutDashboard },
    { id: 'upload', label: 'Data Source', icon: TbDatabaseImport },
  ];

  const handleRemoveSource = async (e, sourceId) => {
    e.stopPropagation();
    setRemovingId(sourceId);
    try {
      await deleteSource(sourceId);
      onDatasetsChanged?.();
    } catch {
      // leave it in place on failure; user can retry
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <>
      {/* Mobile overlay */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden transition-opacity"
          onClick={() => setIsMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed lg:static inset-y-0 left-0 z-50
        w-[248px] bg-[#1C1917] border-r border-white/[0.06]
        flex flex-col h-full transform transition-transform duration-300 ease-in-out
        ${isMobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Logo Area */}
        <div className="h-16 flex items-center px-5 shrink-0">
          <span className="font-serif text-xl text-zinc-100 tracking-tight">
            Voice BI
          </span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto pb-6 px-3 space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  onViewChange(item.id);
                  setIsMobileOpen(false);
                }}
                className={`nav-item w-full flex items-center gap-3 px-3 py-2.5 text-sm font-medium ${isActive ? 'is-active' : ''}`}
              >
                <Icon className="w-[18px] h-[18px]" />
                {item.label}
              </button>
            );
          })}

          {/* Data Sources — pick which "session" queries run against */}
          {sources.length > 0 && (
            <div className="pt-7">
              <div className="text-[11px] font-medium text-zinc-600 uppercase tracking-wider mb-2 px-3">
                Data Sources
              </div>
              <div className="space-y-0.5">
                {sources.map(src => {
                  const isActive = src.id === activeSourceId;
                  const SrcIcon = src.type === 'csv' ? TbFileSpreadsheet : TbDatabase;
                  return (
                    <button
                      key={src.id}
                      onClick={() => { onSelectSource?.(src.id); onViewChange('dashboard'); setIsMobileOpen(false); }}
                      className={`nav-item group w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left ${isActive ? 'is-active' : ''}`}
                      title={src.label}
                    >
                      <SrcIcon className="w-4 h-4 shrink-0" />
                      <span className="flex-1 min-w-0 truncate">{src.label}</span>
                      <span className="text-[10px] text-zinc-600 shrink-0">{src.tables.length}</span>
                      {src.type !== 'csv' && (
                        removingId === src.id ? (
                          <TbLoader2 className="w-3.5 h-3.5 animate-spin text-zinc-500 shrink-0" />
                        ) : (
                          <span
                            role="button"
                            tabIndex={0}
                            onClick={(e) => handleRemoveSource(e, src.id)}
                            className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 p-0.5 rounded transition-all shrink-0"
                            title={`Disconnect ${src.label}`}
                          >
                            <TbTrash className="w-3.5 h-3.5" />
                          </span>
                        )
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </nav>

        {/* Footer — connection status */}
        <div className="p-4 border-t border-white/[0.06]">
          <Header isProcessing={isProcessing} />
        </div>
      </aside>
    </>
  );
}
