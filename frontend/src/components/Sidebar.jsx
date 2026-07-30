import { useState } from 'react';
import {
  TbDatabaseImport, TbLayoutDashboard,
  TbDatabase, TbFileSpreadsheet, TbTrash, TbLoader2,
  TbClipboardCheck, TbLogout, TbSun, TbMoon,
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
  user,
  onLogout,
  theme,
  onToggleTheme,
}) {
  const [removingId, setRemovingId] = useState(null);

  const navItems = [
    { id: 'dashboard', label: 'Analysis Workspace', icon: TbLayoutDashboard },
    { id: 'upload', label: 'Data Source', icon: TbDatabaseImport },
    { id: 'quality', label: 'Data Quality', icon: TbClipboardCheck },
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
        w-[248px] bg-surface-alt border-r border-black/[0.06]
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
          <div className="text-[10px] font-semibold text-[#9C7A3E] uppercase tracking-wider mb-2 px-3">
            Workspace
          </div>
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

        {/* Footer — connection status + account */}
        <div className="p-4 border-t border-black/[0.06] space-y-3">
          {onToggleTheme && (
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-zinc-500 flex items-center gap-1.5">
                {theme === 'dark' ? <TbMoon className="w-3.5 h-3.5" /> : <TbSun className="w-3.5 h-3.5" />}
                {theme === 'dark' ? 'Dark' : 'Light'}
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={theme === 'dark'}
                onClick={onToggleTheme}
                title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
                className={`relative w-10 h-5 rounded-full shrink-0 transition-colors border ${
                  theme === 'dark' ? 'bg-[#9C4A2A] border-[#9C4A2A]' : 'bg-black/10 border-black/10'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-3.5 h-3.5 rounded-full bg-white shadow-sm transition-transform ${
                    theme === 'dark' ? 'translate-x-5' : ''
                  }`}
                />
              </button>
            </div>
          )}
          <Header isProcessing={isProcessing} />
          {onLogout && (
            <div className="flex items-center justify-between gap-2">
              {user?.email && (
                <span className="text-xs text-zinc-500 truncate" title={user.email}>{user.email}</span>
              )}
              <button
                type="button"
                onClick={onLogout}
                className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-[#9C4A2A] transition-colors shrink-0"
                title="Log out"
              >
                <TbLogout className="w-3.5 h-3.5" />
                Log out
              </button>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
