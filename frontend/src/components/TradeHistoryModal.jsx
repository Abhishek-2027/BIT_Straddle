import React, { useState } from 'react';
import { X, History, FileText, CheckCircle2 } from 'lucide-react';

export default function TradeHistoryModal({ orders = [], events = [], onClose }) {
  const [activeTab, setActiveTab] = useState('orders');

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#171B21] border border-borderDark rounded-2xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-borderDark/60">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center text-blue-400">
              <History className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Execution & Trade History</h2>
              <p className="text-xs text-gray-400">Full audit log of submitted orders and strategy events</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg hover:bg-borderDark flex items-center justify-center text-gray-400 hover:text-white"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab switch */}
        <div className="flex items-center gap-2 px-5 pt-3 border-b border-borderDark/40">
          <button
            onClick={() => setActiveTab('orders')}
            className={`pb-2 text-xs font-bold transition-colors border-b-2 flex items-center gap-1.5 ${
              activeTab === 'orders'
                ? 'border-[#20C978] text-[#20C978]'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Orders ({orders.length})</span>
          </button>
          <button
            onClick={() => setActiveTab('events')}
            className={`pb-2 text-xs font-bold transition-colors border-b-2 flex items-center gap-1.5 ${
              activeTab === 'events'
                ? 'border-[#20C978] text-[#20C978]'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Events ({events.length})</span>
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto flex-1">
          {activeTab === 'orders' ? (
            orders.length === 0 ? (
              <div className="text-center py-12 text-gray-500 text-xs">
                No orders recorded in this session yet.
              </div>
            ) : (
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-gray-500 text-[11px] font-semibold border-b border-borderDark/40 pb-2">
                    <th className="pb-2 font-medium">Order ID</th>
                    <th className="pb-2 font-medium">Instrument</th>
                    <th className="pb-2 font-medium">Side</th>
                    <th className="pb-2 font-medium">Qty</th>
                    <th className="pb-2 font-medium">Price</th>
                    <th className="pb-2 font-medium text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-borderDark/20">
                  {orders.map((o, idx) => (
                    <tr key={idx} className="text-gray-300 font-medium">
                      <td className="py-2.5 font-mono text-[11px] text-gray-400">{o.order_id}</td>
                      <td className="py-2.5 font-mono text-[11px] text-gray-300">{o.instrument_id}</td>
                      <td className="py-2.5">
                        <span className={`font-semibold ${o.side === 'SELL' || o.side === '2' ? 'text-[#EF4444]' : 'text-[#20C978]'}`}>
                          {o.side === '2' ? 'SELL' : o.side === '1' ? 'BUY' : o.side}
                        </span>
                      </td>
                      <td className="py-2.5 tabular-nums">{o.qty}</td>
                      <td className="py-2.5 tabular-nums text-white">${o.price}</td>
                      <td className="py-2.5 text-right">
                        <span className={`inline-block px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                          o.status === 'FILLED'
                            ? 'bg-[#1E2C22] text-[#20C978] border-[#20C978]/30'
                            : o.status === 'CANCELED'
                            ? 'bg-amber-950/40 text-amber-400 border-amber-500/30'
                            : 'bg-gray-800 text-gray-300 border-gray-700'
                        }`}>
                          {o.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          ) : (
            <div className="flex flex-col gap-2">
              {events.slice(-50).reverse().map((ev, idx) => (
                <div key={idx} className="flex items-start justify-between bg-[#12151A] border border-borderDark/60 rounded-xl p-3 text-xs">
                  <div className="flex items-start gap-2.5">
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-[#1A1F26] text-gray-300 border border-borderDark font-mono">
                      {ev.code}
                    </span>
                    <span className="text-gray-200 font-medium">{ev.text}</span>
                  </div>
                  <span className="text-[10px] text-gray-500 font-mono shrink-0 ml-4">
                    {ev.timestamp ? ev.timestamp.slice(11, 19) : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-borderDark/60 flex justify-end">
          <button onClick={onClose} className="btn-outline px-5 py-2 text-xs font-semibold">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
