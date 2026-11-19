import React from 'react';
import { ListFilter, ArrowRight } from 'lucide-react';

export default function TradeHistoryCard({ orders = [], events = [], onViewAll }) {
  // Parse executed orders and events into clean transaction rows
  const transactions = [];

  if (Array.isArray(orders) && orders.length > 0) {
    orders.forEach((o) => {
      const isCall = String(o.instrument_id || '').includes('-C-') || o.leg === 'CALL';
      const isSell = o.side === 'SELL' || o.side === '2';
      const action = `${isSell ? 'Sell' : 'Buy'} ${isCall ? 'Call' : 'Put'}`;

      const d = o.timestamps?.submitted ? new Date(o.timestamps.submitted) : new Date();
      const timeStr = `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;

      transactions.push({
        id: o.order_id || `${o.instrument_id}-${o.side}-${d.toISOString()}`,
        time: timeStr,
        action,
        actionType: isSell ? 'short' : 'long',
        price: o.price && o.price !== 'MARKET' ? `$${Number(o.price).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : 'Market',
        qty: o.qty || '--',
        status: o.status || 'Unknown',
      });
    });
  }

  const displayRows = transactions.slice(0, 3);

  return (
    <div className="card h-[160px] flex flex-col justify-between">
      {/* Title & View All */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-blue-500/10 flex items-center justify-center text-blue-400">
            <ListFilter className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">Trade History</span>
        </div>

        <button
          onClick={onViewAll}
          className="text-xs font-semibold text-gray-400 hover:text-white flex items-center gap-1 transition-colors"
        >
          <span>View All</span>
          <ArrowRight className="w-3 h-3" />
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        {displayRows.length === 0 ? (
          <div className="py-6 text-center text-xs text-gray-500">No exchange-confirmed orders yet.</div>
        ) : <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-gray-500 text-[11px] font-semibold border-b border-borderDark/40 pb-1">
              <th className="pb-1.5 font-medium">Time</th>
              <th className="pb-1.5 font-medium">Action</th>
              <th className="pb-1.5 font-medium">Price</th>
              <th className="pb-1.5 font-medium">Qty</th>
              <th className="pb-1.5 font-medium text-right">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-borderDark/20">
            {displayRows.map((row) => {
              const actionColor =
                row.actionType === 'long'
                  ? 'text-[#20C978]'
                  : row.actionType === 'short'
                  ? 'text-[#EF4444]'
                  : 'text-amber-400';

              return (
                <tr key={row.id} className="text-gray-300 font-medium">
                  <td className="py-1.5 tabular-nums text-gray-400">{row.time}</td>
                  <td className={`py-1.5 font-semibold ${actionColor}`}>{row.action}</td>
                  <td className="py-1.5 tabular-nums text-gray-200">{row.price}</td>
                  <td className="py-1.5 tabular-nums text-gray-300">{row.qty}</td>
                  <td className="py-1.5 text-right">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                      row.status === 'FILLED'
                        ? 'bg-[#1E2C22] text-[#20C978] border-[#20C978]/30'
                        : row.status === 'CANCELED'
                        ? 'bg-amber-950/40 text-amber-400 border-amber-500/30'
                        : 'bg-gray-800 text-gray-300 border-gray-700'
                    }`}>
                      {row.status}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>}
      </div>
    </div>
  );
}
