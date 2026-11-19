import React from 'react';
import { LayoutDashboard, History, Settings, Info } from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, isConnected, environment = 'demo' }) {
  const environmentLabel = environment === 'demo'
    ? 'Demo Trading'
    : environment === 'mainnet'
      ? 'Mainnet'
      : 'Testnet';
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'history', label: 'Trade History', icon: History },
    { id: 'settings', label: 'Settings', icon: Settings },
    { id: 'about', label: 'About', icon: Info },
  ];

  return (
    <aside className="w-[230px] min-h-screen bg-sidebar border-r border-borderDark flex flex-col justify-between p-5 select-none shrink-0">
      {/* Top Branding */}
      <div>
        <div className="flex items-center gap-3 mb-8">
          {/* Orange Bitcoin Logo Circle */}
          <div className="w-10 h-10 rounded-full bg-[#F7931A] flex items-center justify-center shadow-md shadow-orange-500/20 shrink-0">
            <span className="text-white font-extrabold text-xl leading-none">₿</span>
          </div>
          <div>
            <div className="text-white font-bold text-base tracking-tight leading-tight">BTC</div>
            <div className="text-gray-400 text-xs tracking-normal">Straddle Monitor</div>
          </div>
        </div>

        {/* Navigation Menu */}
        <nav className="flex flex-col gap-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 ${
                  isActive
                    ? 'bg-[#1E2C22] text-[#20C978] shadow-sm'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-[#1A1F26]'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-[#20C978]' : 'text-gray-400'}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom Bybit Status & Branding */}
      <div className="flex flex-col gap-4">
        {/* Connection status card */}
        <div className="bg-[#171B21] border border-borderDark rounded-xl p-3">
          <div className="flex items-center gap-2">
            <span className={`pulse-dot ${isConnected ? 'bg-[#20C978]' : 'bg-red-500'}`} />
            <span className="text-xs font-medium text-gray-200">Bybit {environmentLabel}</span>
          </div>
          <div className={`text-[11px] font-semibold pl-4 ${isConnected ? 'text-[#20C978]' : 'text-red-400'}`}>
            {isConnected ? 'Connected' : 'Disconnected'}
          </div>
        </div>

        {/* Bybit Wordmark */}
        <div className="text-center">
          <div className="text-[10px] text-gray-500 font-medium mb-1">Powered by</div>
          <div className="flex items-center justify-center gap-0.5 font-bold tracking-wider text-sm text-gray-200">
            <span className="text-white">BYB</span>
            <span className="inline-block w-1.5 h-3 bg-[#F7931A] rounded-[1px] mx-[1px]"></span>
            <span className="text-white">T</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
