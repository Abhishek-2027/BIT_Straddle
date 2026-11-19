import React from 'react';
import { ResponsiveContainer, AreaChart, Area } from 'recharts';

export default function BtcPriceCard({ marketData }) {
  const price = marketData?.price;
  const change24h = marketData?.change24h;
  const high24h = marketData?.high24h;
  const low24h = marketData?.low24h;
  const sparkline = marketData?.sparkline?.length > 0
    ? marketData.sparkline.map((val, idx) => ({ i: idx, val }))
    : [];

  const isPositive = Number(change24h) >= 0;

  return (
    <div className="card flex items-center justify-between gap-4 h-[130px]">
      {/* Left side: Icon + Price info */}
      <div className="flex items-center gap-4">
        {/* Large Bitcoin Icon */}
        <div className="w-14 h-14 rounded-full bg-[#F7931A] flex items-center justify-center shadow-lg shadow-orange-500/20 shrink-0">
          <span className="text-white font-extrabold text-2xl leading-none">₿</span>
        </div>

        {/* Details */}
        <div className="flex flex-col">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">BTC Price</span>
          <div className="flex items-center gap-2.5 mt-0.5">
            <span className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight tabular-nums">
              {price != null ? `$${Number(price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'Unavailable'}
            </span>
            {change24h != null && (
              <span className={`text-xs font-bold px-2 py-0.5 rounded-md flex items-center gap-1 ${
                isPositive ? 'text-[#20C978] bg-[#20C978]/10' : 'text-[#EF4444] bg-[#EF4444]/10'
              }`}>
                {isPositive ? '▲ +' : '▼ '}
                {Math.abs(Number(change24h))}%
              </span>
            )}
          </div>

          <div className="text-[11px] text-gray-400 mt-1 font-medium tabular-nums">
            24h High: {high24h != null ? `$${Number(high24h).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '--'} <span className="text-gray-600">|</span> 24h Low: {low24h != null ? `$${Number(low24h).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '--'}
          </div>
        </div>
      </div>

      {/* Right side: Mini Sparkline Chart */}
      <div className="w-[140px] sm:w-[170px] h-16 shrink-0">
        {sparkline.length > 0 && <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={sparkline} margin={{ top: 4, right: 2, left: 2, bottom: 0 }}>
            <defs>
              <linearGradient id="btcSparkGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#20C978" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#20C978" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="val"
              stroke="#20C978"
              strokeWidth={2}
              fill="url(#btcSparkGrad)"
              isAnimationActive={false}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>}
      </div>
    </div>
  );
}
