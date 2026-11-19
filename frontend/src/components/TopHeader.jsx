import React from 'react';

export default function TopHeader({ isConnected, environment = 'demo' }) {
  const environmentLabel = environment === 'demo'
    ? 'Demo Trading'
    : environment === 'mainnet'
      ? 'Mainnet'
      : 'Testnet';

  return (
    <header className="flex items-center justify-end gap-3 pb-4">
      {/* Live Updates indicator */}
      <div className="flex items-center gap-2 bg-[#171B21] border border-borderDark px-3 py-1.5 rounded-full text-xs font-medium text-gray-300">
        <span className={`pulse-dot ${isConnected ? 'bg-[#20C978]' : 'bg-red-500'}`} />
        <span>Live Updates · 2s</span>
      </div>

      <div className="h-4 w-[1px] bg-borderDark" />

      <div className="bg-[#171B21] border border-borderDark px-3.5 py-1.5 rounded-xl text-xs font-semibold text-gray-200">
        Bybit {environmentLabel}
      </div>
    </header>
  );
}
