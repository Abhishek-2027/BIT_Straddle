import React from 'react';
import { X, Info, CheckCircle, Zap } from 'lucide-react';

export default function AboutModal({ onClose, environment = 'demo' }) {
  const environmentLabel = environment === 'demo'
    ? 'Demo Trading'
    : environment === 'mainnet'
      ? 'Mainnet'
      : 'Testnet';

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#171B21] border border-borderDark rounded-2xl w-full max-w-lg p-6 shadow-2xl relative">
        <div className="flex items-center justify-between pb-4 border-b border-borderDark/60">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#20C978]/10 flex items-center justify-center text-[#20C978]">
              <Info className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">BTC Straddle Monitor</h2>
              <p className="text-xs text-gray-400">Institutional ATM Options Trading Terminal</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-lg hover:bg-borderDark flex items-center justify-center text-gray-400 hover:text-white"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex flex-col gap-4 mt-5 text-xs text-gray-300">
          <p className="leading-relaxed">
            This platform runs an automated <strong className="text-white">BTC ATM Short Straddle</strong> algorithmic trading system engineered with <strong className="text-white">NautilusTrader</strong> and connected to Bybit <strong className="text-white">{environmentLabel}</strong>.
          </p>

          <div className="bg-[#12151A] border border-borderDark rounded-xl p-4 flex flex-col gap-2.5">
            <div className="font-bold text-white text-xs flex items-center gap-2">
              <Zap className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
              <span>Core Trading Logic</span>
            </div>
            <div className="flex items-start gap-2 text-gray-400">
              <CheckCircle className="w-3.5 h-3.5 text-[#20C978] shrink-0 mt-0.5" />
              <span>Dynamically selects the nearest expiry At-The-Money (ATM) BTC Call and Put pair.</span>
            </div>
            <div className="flex items-start gap-2 text-gray-400">
              <CheckCircle className="w-3.5 h-3.5 text-[#20C978] shrink-0 mt-0.5" />
              <span>Submits simultaneous short orders to capture premium decay and volatility contraction.</span>
            </div>
            <div className="flex items-start gap-2 text-gray-400">
              <CheckCircle className="w-3.5 h-3.5 text-[#20C978] shrink-0 mt-0.5" />
              <span>Real-time risk engine tracking buyback valuation with automated 1% Stop-Loss and 2% Take-Profit.</span>
            </div>
          </div>

          <div className="flex items-center justify-between text-[11px] text-gray-500 pt-2 border-t border-borderDark/40">
            <span>Exchange environment: {environmentLabel}</span>
            <span>Version 2.0.0</span>
          </div>
        </div>

        <div className="mt-5 flex justify-end">
          <button onClick={onClose} className="btn-green px-5 py-2 text-xs font-bold text-black">
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
