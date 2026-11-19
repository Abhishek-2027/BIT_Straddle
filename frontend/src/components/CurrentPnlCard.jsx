import React from 'react';
import { BarChart2, ShieldCheck } from 'lucide-react';

export default function CurrentPnlCard({ risk, state = 'IDLE', config }) {
  const isLive = risk?.state === 'OPEN' || risk?.is_live;
  const isClosed = risk?.state === 'CLOSED' || state === 'CLOSED';
  const entryPremium = risk?.entry_premium != null ? Number(risk.entry_premium) : null;
  const buybackCost = risk?.buyback_cost != null ? Number(risk.buyback_cost) : null;
  let pnl = null;
  let pnlPercent = null;
  let statusText = 'No confirmed trade';

  if (isLive && entryPremium !== null && buybackCost !== null) {
    pnl = Number((entryPremium - buybackCost).toFixed(2));
    pnlPercent = entryPremium > 0 ? Number(((pnl / entryPremium) * 100).toFixed(2)) : null;
    statusText = 'Unrealized · Exchange-confirmed position';
  } else if (isClosed) {
    pnl = risk?.realized_pnl != null ? Number(risk.realized_pnl) : null;
    pnlPercent = risk?.realized_pnl_pct != null ? Number(risk.realized_pnl_pct) : null;
    statusText = pnl === null ? 'Closed · realized PnL unavailable' : 'Realized · Position closed';
  } else if (entryPremium !== null) {
    statusText = 'Indicative · Not a position';
  }

  const isPositive = pnl !== null && pnl >= 0;
  const pnlColor = pnl === null || pnl === 0
    ? 'text-gray-300'
    : isPositive
      ? 'text-[#20C978]'
      : 'text-[#EF4444]';

  return (
    <div className="card h-[145px] flex flex-col justify-between">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-[#20C978]/10 flex items-center justify-center text-[#20C978]">
            <BarChart2 className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">Current PnL</span>
        </div>
        <div className="flex items-center gap-1 text-[10px] font-semibold text-[#20C978] bg-[#1E2C22] px-2 py-0.5 rounded-full border border-[#20C978]/30">
          <ShieldCheck className="w-3 h-3" />
          <span>SL: {config?.sl_pct != null ? `${Number((config.sl_pct * 100).toFixed(1))}%` : '1%'} | TP: {config?.tp_pct != null ? `${Number((config.tp_pct * 100).toFixed(1))}%` : '2%'}</span>
        </div>
      </div>

      <div className="flex items-end justify-between">
        <div>
          <div className={`text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums ${pnlColor}`}>
            {pnl === null ? '--' : pnl === 0 ? '$0.00' : isPositive ? `+$${pnl.toFixed(2)}` : `-$${Math.abs(pnl).toFixed(2)}`}
          </div>
          <div className="mt-1 flex items-center gap-2">
            <span className="text-xs font-bold px-2 py-0.5 rounded-md inline-flex items-center gap-1 text-gray-400 bg-gray-800">
              {pnlPercent === null ? '--' : `${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%`}
            </span>
            <span className="text-[10px] text-gray-400 font-medium truncate max-w-[190px]">{statusText}</span>
          </div>
        </div>

      </div>

      <div className="flex items-center justify-between pt-1.5 border-t border-borderDark/40 text-[10px] text-gray-400 font-medium">
        <span>
          {isClosed ? 'Traded Entry: ' : isLive ? 'Live Entry: ' : 'Indicative Entry: '}
          <strong className="text-white tabular-nums">{entryPremium === null ? '--' : `$${entryPremium.toFixed(2)}`}</strong>
        </span>
        <span>
          {isClosed ? 'Exit Cost: ' : isLive ? 'Buyback (Ask): ' : 'Current Ask: '}
          <strong className="text-white tabular-nums">{buybackCost === null ? '--' : `$${buybackCost.toFixed(2)}`}</strong>
        </span>
        <span>
          Status: <strong className={isLive ? 'text-[#20C978]' : isClosed ? 'text-amber-400' : 'text-gray-300'}>
            {isLive ? 'Active' : isClosed ? 'Closed' : 'Standby'}
          </strong>
        </span>
      </div>
    </div>
  );
}
