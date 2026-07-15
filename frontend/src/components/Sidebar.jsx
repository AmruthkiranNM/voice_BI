import { TbMessageChatbot, TbDatabaseImport, TbSettings, TbLayoutDashboard, TbHistory } from 'react-icons/tb';

export default function Sidebar({
  currentView,
  onViewChange,
  isMobileOpen,
  setIsMobileOpen
}) {
  const navItems = [
    { id: 'dashboard', label: 'Analysis Workspace', icon: TbLayoutDashboard },
    { id: 'upload', label: 'Data Source', icon: TbDatabaseImport },
  ];

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
        w-[280px] bg-[#09090b] border-r border-white/10
        flex flex-col h-full transform transition-transform duration-300 ease-in-out
        ${isMobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Logo Area */}
        <div className="h-16 flex items-center px-6 border-b border-white/5 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center border border-blue-500/30">
              <TbMessageChatbot className="w-5 h-5 text-blue-500" />
            </div>
            <span className="font-semibold text-zinc-100 text-lg tracking-tight">
              Voice BI
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-6 px-4 space-y-1">
          <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3 px-2">
            Main Menu
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
                className={`
                  w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all
                  ${isActive
                    ? 'active-pill shadow-sm'
                    : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5 border border-transparent'}
                `}
              >
                <Icon className={`w-5 h-5 ${isActive ? 'text-blue-300' : 'text-zinc-500'}`} />
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Footer Area */}
        <div className="p-4 border-t border-white/5">
          <button
            disabled
            title="Settings — coming soon"
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 cursor-not-allowed"
          >
            <TbSettings className="w-5 h-5 text-zinc-600" />
            Settings
            <span className="ml-auto text-[10px] text-zinc-600 uppercase tracking-wide">Soon</span>
          </button>
          
          <div className="mt-4 px-3 py-3 rounded-lg bg-white/[0.02] border border-white/5 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-600 to-violet-600 flex items-center justify-center text-xs font-medium text-white shadow-inner">
              US
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-zinc-200 truncate">User Session</p>
              <p className="text-xs text-zinc-500 truncate">Enterprise Plan</p>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
