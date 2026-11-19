import React, { useState, useEffect, useRef, useMemo } from 'react';
import { TrendingUp, Award, ShieldCheck } from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';

export default function MainPnlChart({ risk, currentPnl = 0.0, state = 'IDLE' }) {
  const [viewMode, setViewMode] = useState('percent'); // 'percent' | 'usdt'
  const [chartData, setChartData] = useState([]);
  const historyRef = useRef([]);

  // Calculate Level 2 Risk Thresholds from backend risk snapshot
  const {
    entryPremium,
    buybackCost,
    slThreshold,
    tpThreshold,
    tpPnl,
    slPnl,
    isClosed,
    realizedPnl,
    exitReason,
  } = useMemo(() => {
    const entry = risk?.entry_premium != null ? Number(risk.entry_premium) : null;
    const buyback = risk?.buyback_cost != null ? Number(risk.buyback_cost) : null;
    const sl = risk?.sl_threshold != null ? Number(risk.sl_threshold) : null;
    const tp = risk?.tp_threshold != null ? Number(risk.tp_threshold) : null;
    const tpP = entry !== null && tp !== null ? Number((entry - tp).toFixed(2)) : null;
    const slP = entry !== null && sl !== null ? Number((entry - sl).toFixed(2)) : null;
    const closed = risk?.state === 'CLOSED' || state === 'CLOSED';
    const rPnl = risk?.realized_pnl != null ? Number(risk.realized_pnl) : null;
    const reason = risk?.exit_reason || '';

    return {
      entryPremium: entry,
      buybackCost: buyback,
      slThreshold: sl,
      tpThreshold: tp,
      tpPnl: tpP,
      slPnl: slP,
      isClosed: closed,
      realizedPnl: rPnl,
      exitReason: reason,
    };
  }, [
    risk?.entry_premium,
    risk?.buyback_cost,
    risk?.sl_threshold,
    risk?.tp_threshold,
    risk?.state,
    risk?.realized_pnl,
    risk?.exit_reason,
    state,
  ]);

  // Accumulate live points from backend risk updates in real time
  useEffect(() => {
    if (
      risk
      && risk.entry_premium != null
      && risk.buyback_cost != null
      && (risk.is_live === true || (risk.state === 'CLOSED' && risk.realized_pnl != null))
    ) {
      const entry = Number(risk.entry_premium);
      const buyback = Number(risk.buyback_cost);
      let livePnl = Number((entry - buyback).toFixed(2));
      let livePct = entry > 0 ? Number(((livePnl / entry) * 100).toFixed(2)) : 0;

      if (risk.state === 'CLOSED' && risk.realized_pnl != null) {
        livePnl = Number(risk.realized_pnl);
        livePct = Number(risk.realized_pnl_pct || 0);
      }

      const now = Date.now();

      const last = historyRef.current[historyRef.current.length - 1];
      if (!last || now - last.time > 1000) {
        historyRef.current.push({
          time: now,
          pnl: livePnl,
          pnlPct: livePct,
          buyback: buyback,
          entry: entry,
        });
        if (historyRef.current.length > 300) {
          historyRef.current = historyRef.current.slice(-300);
        }
        setChartData([...historyRef.current]);
      }
    }
  }, [risk?.entry_premium, risk?.buyback_cost, risk?.realized_pnl, risk?.state]);

  const latestPoint = chartData.length > 0 ? chartData[chartData.length - 1] : null;
  const latestPnl = latestPoint?.pnl ?? null;
  const latestPct = latestPoint?.pnlPct ?? null;
  const isPositive = latestPnl !== null && latestPnl >= 0;

  const formatTime = (ts) => {
    const d = new Date(ts);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  };

  const formatYAxis = (val) => {
    if (viewMode === 'percent') {
      if (val === 0) return '0.0%';
      return val > 0 ? `+${val.toFixed(1)}%` : `${val.toFixed(1)}%`;
    }
    if (val === 0) return '$0.00';
    return val > 0 ? `+$${val.toFixed(2)}` : `-$${Math.abs(val).toFixed(2)}`;
  };

  // Dynamic Y-axis domains
  const yDomain = useMemo(() => {
    if (viewMode === 'percent') {
      return [-2.0, 3.0];
    }
    const maxVal = Math.max((tpPnl ?? 0) * 1.5, 0.15);
    const minVal = Math.min((slPnl ?? 0) * 1.5, -0.1);
    return [Number(minVal.toFixed(2)), Number(maxVal.toFixed(2))];
  }, [viewMode, tpPnl, slPnl]);

  const yTicks = useMemo(() => {
    if (viewMode === 'percent') {
      return [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0];
    }
    return undefined;
  }, [viewMode]);

  return (
    <div className="card flex flex-col justify-between h-[375px]">
      {/* Header with Title, Level 2 Badges & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-[#20C978]/10 flex items-center justify-center text-[#20C978]">
            <TrendingUp className="w-4 h-4" />
          </div>
          <span className="text-sm font-bold text-white tracking-tight">PnL Chart</span>
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#1E2C22] text-[#20C978] border border-[#20C978]/40 shadow-[0_0_10px_rgba(32,201,120,0.15)]">
            <Award className="w-3 h-3" />
            Level 2 Automated Risk
          </span>
        </div>

        {/* View mode toggle & Time range */}
        <div className="flex items-center gap-2">
          {/* Unit Toggle */}
          <div className="flex items-center bg-[#12151A] border border-borderDark p-0.5 rounded-lg text-xs font-semibold">
            <button
              onClick={() => setViewMode('percent')}
              className={`px-2.5 py-1 rounded-md transition-all ${
                viewMode === 'percent'
                  ? 'bg-[#20C978] text-black font-bold shadow-sm'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              % Return
            </button>
            <button
              onClick={() => setViewMode('usdt')}
              className={`px-2.5 py-1 rounded-md transition-all ${
                viewMode === 'usdt'
                  ? 'bg-[#20C978] text-black font-bold shadow-sm'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              USDT ($)
            </button>
          </div>

        </div>
      </div>

      {/* Level 2 Live Risk Status Strip - 100% Real & Live Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2 p-2 rounded-xl bg-[#12151A]/80 border border-borderDark/60 text-[11px]">
        <div className="flex flex-col">
          <span className="text-gray-400 text-[10px]">
            {isClosed ? 'Traded Entry' : state === 'OPEN' ? 'Live Entry' : 'Proj. Entry'}
          </span>
          <span className="text-white font-mono font-bold">{entryPremium === null ? '--' : `$${entryPremium.toFixed(2)} USDT`}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-gray-400 text-[10px]">
            {isClosed ? 'Exit Buyback' : 'Buyback Cost (Ask)'}
          </span>
          <span className="text-white font-mono font-bold">{buybackCost === null ? '--' : `$${buybackCost.toFixed(2)} USDT`}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-gray-400 text-[10px]">
            {isClosed ? 'Realized PnL' : 'TP Target (+2%)'}
          </span>
          {isClosed ? (
            <span
              className={`font-mono font-bold ${
                Number(realizedPnl) >= 0 ? 'text-[#20C978]' : 'text-[#EF4444]'
              }`}
            >
              {realizedPnl == null
                ? 'PnL unavailable'
                : `${Number(realizedPnl) >= 0 ? '+' : '-'}$${Math.abs(Number(realizedPnl)).toFixed(2)}`}
              {realizedPnl != null && ` · ${exitReason || 'Closed'}`}
            </span>
          ) : (
            <span className="text-[#20C978] font-mono font-bold">
              {tpThreshold === null || tpPnl === null ? '--' : `≤ $${tpThreshold.toFixed(2)} (+$${tpPnl.toFixed(2)})`}
            </span>
          )}
        </div>
        <div className="flex flex-col">
          <span className="text-gray-400 text-[10px]">
            {isClosed ? 'Status' : 'SL Limit (-1%)'}
          </span>
          {isClosed ? (
            <span className="text-amber-400 font-mono font-bold">Ready to Re-Arm</span>
          ) : (
            <span className="text-[#EF4444] font-mono font-bold">
              {slThreshold === null || slPnl === null ? '--' : `≥ $${slThreshold.toFixed(2)} (-$${Math.abs(slPnl).toFixed(2)})`}
            </span>
          )}
        </div>
      </div>

      {/* Main Chart Area */}
      <div className="flex-1 w-full relative" style={{ minHeight: 195 }}>
        {chartData.length > 0 ? <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 15, right: 40, left: -5, bottom: 0 }}>
            <defs>
              <linearGradient id="pnlAreaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#20C978" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#20C978" stopOpacity={0.0} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="#1F242C" vertical={false} />

            <XAxis
              dataKey="time"
              tickFormatter={formatTime}
              stroke="#4B5563"
              tick={{ fill: '#848E9C', fontSize: 11 }}
              minTickGap={45}
              axisLine={{ stroke: '#292E36' }}
              tickLine={false}
            />

            <YAxis
              stroke="#4B5563"
              tickFormatter={formatYAxis}
              tick={{ fill: '#848E9C', fontSize: 11 }}
              domain={yDomain}
              ticks={yTicks}
              axisLine={false}
              tickLine={false}
              width={60}
            />

            {/* Zero Breakeven Reference Line */}
            <ReferenceLine y={0} stroke="#6B7280" strokeDasharray="4 4" strokeWidth={1} />

            {/* Level 2 Take-Profit (+2%) Threshold Line */}
            {tpPnl !== null && <ReferenceLine
              y={viewMode === 'percent' ? 2.0 : tpPnl}
              stroke="#20C978"
              strokeDasharray="5 3"
              strokeWidth={1.5}
              label={{
                value: viewMode === 'percent' ? 'TP (+2.0%)' : `TP (+2%): +$${tpPnl.toFixed(2)}`,
                fill: '#20C978',
                fontSize: 10,
                position: 'right',
                offset: 5,
              }}
            />}

            {/* Level 2 Stop-Loss (-1%) Threshold Line */}
            {slPnl !== null && <ReferenceLine
              y={viewMode === 'percent' ? -1.0 : slPnl}
              stroke="#EF4444"
              strokeDasharray="5 3"
              strokeWidth={1.5}
              label={{
                value: viewMode === 'percent' ? 'SL (-1.0%)' : `SL (-1%): -$${Math.abs(slPnl).toFixed(2)}`,
                fill: '#EF4444',
                fontSize: 10,
                position: 'right',
                offset: 5,
              }}
            />}

            <Tooltip
              contentStyle={{
                backgroundColor: '#15191F',
                border: '1px solid #292E36',
                borderRadius: '12px',
                fontSize: '12px',
                color: '#fff',
                boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
              }}
              labelFormatter={formatTime}
              formatter={(value, name) => [
                viewMode === 'percent'
                  ? `${Number(value).toFixed(2)}%`
                  : `$${Number(value).toFixed(2)} USDT`,
                name === 'pnlPct' ? 'Return (%)' : 'Live PnL',
              ]}
            />

            <Area
              type="monotone"
              dataKey={viewMode === 'percent' ? 'pnlPct' : 'pnl'}
              name={viewMode === 'percent' ? 'pnlPct' : 'pnl'}
              stroke="#20C978"
              strokeWidth={2.2}
              fill="url(#pnlAreaGrad)"
              isAnimationActive={false}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer> : (
          <div className="h-full flex items-center justify-center text-xs text-gray-500">
            No exchange-confirmed open-trade PnL data.
          </div>
        )}

        {/* Floating pill near end of line */}
        <div className="absolute top-1 right-2 pointer-events-none">
          <div className="bg-[#1E2C22] border border-[#20C978]/40 text-[#20C978] text-xs font-bold px-2 py-0.5 rounded-md shadow-lg flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#20C978] animate-pulse" />
            <span>
              {latestPnl === null
                ? 'No confirmed trade'
                : latestPnl === 0
                ? '$0.00 (0.00%)'
                : isPositive
                ? `+$${latestPnl.toFixed(2)} (+${latestPct.toFixed(2)}%)`
                : `-$${Math.abs(latestPnl).toFixed(2)} (${latestPct.toFixed(2)}%)`}
            </span>
          </div>
        </div>
      </div>

      {/* Level 2 Legend & Assignment Info */}
      <div className="flex items-center justify-between pt-2 border-t border-borderDark/40 text-[11px] text-gray-400">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 bg-[#20C978] inline-block" /> Live Trajectory
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 bg-[#20C978] border-dashed border-t inline-block" /> Take-Profit (+2%)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 bg-[#EF4444] border-dashed border-t inline-block" /> Stop-Loss (-1%)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 bg-gray-500 border-dashed border-t inline-block" /> Breakeven ($0)
          </span>
        </div>
        <div className="text-gray-500 font-mono text-[10px]">Valuation: Ask Quotes (IOC)</div>
      </div>
    </div>
  );
}
