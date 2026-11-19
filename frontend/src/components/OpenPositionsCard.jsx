import React from 'react';
import { Box, ArrowUp, ArrowDown } from 'lucide-react';

export default function OpenPositionsCard({ positions = [], quotes = {}, selection }) {
  const strike = selection?.strike
    ? `$${Number(selection.strike).toLocaleString()}`
    : '--';
  const legs = [
    { key: 'CALL', label: 'SHORT CALL', icon: ArrowUp, color: 'text-[#20C978]', bg: 'bg-[#20C978]/15' },
    { key: 'PUT', label: 'SHORT PUT', icon: ArrowDown, color: 'text-[#EF4444]', bg: 'bg-[#EF4444]/15' },
  ];

  return (
    <div className="card h-[190px] flex flex-col justify-between">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-purple-500/10 flex items-center justify-center text-purple-400">
            <Box className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">Open Positions</span>
        </div>
        <span className="text-[10px] text-gray-400 font-mono">
          Strike: <strong className="text-white">{strike}</strong>
        </span>
      </div>

      <div className="flex flex-col gap-2.5">
        {legs.map(({ key, label, icon: Icon, color, bg }) => {
          const position = positions.find((item) => item.leg === key);
          const quote = quotes?.[key.toLowerCase()] || {};
          const entry = Number(position?.avg_entry);
          const isShort = !String(position?.side || 'SHORT').toUpperCase().includes('LONG');
          const closePrice = Number(
            (isShort ? quote.ask : quote.bid)
              ?? (isShort ? position?.current_ask : position?.current_bid),
          );
          const qty = Number(position?.qty);
          const multiplier = Number(position?.multiplier ?? 1);
          const hasPnl = position && entry > 0 && closePrice > 0 && qty > 0 && multiplier > 0 && !quote.is_synthetic;
          const pnl = hasPnl
            ? (isShort ? entry - closePrice : closePrice - entry) * qty * multiplier
            : null;
          const pnlPct = hasPnl
            ? ((isShort ? entry - closePrice : closePrice - entry) / entry) * 100
            : null;
          const profitable = pnl !== null && pnl >= 0;
          const positionLabel = position
            ? `${isShort ? 'SHORT' : 'LONG'} ${key}`
            : label;

          return (
            <div key={key} className="flex items-center justify-between bg-[#12151A] border border-borderDark/80 rounded-xl px-3 py-2">
              <div className="flex items-center gap-2.5">
                <div className={`w-7 h-7 rounded-full ${bg} ${color} flex items-center justify-center shrink-0`}>
                  <Icon className="w-4 h-4 stroke-[2.5]" />
                </div>
                <div>
                  <div className="text-xs font-bold text-white">{positionLabel}</div>
                  <div className="text-[10px] font-mono text-gray-400">
                    {position ? `Qty: ${position.qty}` : 'No open position'}
                  </div>
                </div>
              </div>

              <div className="text-center text-[11px] font-medium text-gray-300 tabular-nums">
                <div>Entry: {position && entry > 0 ? `$${entry.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '--'}</div>
                <div className="text-gray-400">
                  {quote.is_synthetic ? 'Indicative: ' : isShort ? 'Buyback ask: ' : 'Sell bid: '}
                  {Number.isFinite(closePrice) && closePrice > 0 ? `$${closePrice.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '--'}
                </div>
              </div>

              <div className="text-right tabular-nums min-w-[58px]">
                {pnl === null ? (
                  <div className="text-xs text-gray-500">--</div>
                ) : (
                  <>
                    <div className={`text-xs font-bold ${profitable ? 'text-[#20C978]' : 'text-[#EF4444]'}`}>
                      {profitable ? '+' : '-'}${Math.abs(pnl).toFixed(2)}
                    </div>
                    <div className={`text-[10px] font-semibold ${profitable ? 'text-[#20C978]' : 'text-[#EF4444]'}`}>
                      {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                    </div>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
