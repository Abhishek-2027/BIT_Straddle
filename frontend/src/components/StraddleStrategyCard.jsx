import React from 'react';
import { Zap, RotateCw, Square, Play, ShieldAlert } from 'lucide-react';

export default function StraddleStrategyCard({
  state,
  config,
  onArm,
  onDisarm,
  onFlatten,
  onReset,
  onRefresh,
  loading = false,
  actionError = '',
  latestEvent = null,
  statusFeedConnected = false,
  statusMessage = '',
}) {
  const isOpen = state === 'OPEN' || state === 'UNBALANCED';
  const isEntrySubmitted = state === 'ENTRY_SUBMITTED';
  const isArmed = state === 'ARMED' || isEntrySubmitted;
  const isExiting = state === 'EXITING';
  const isStarting = state === 'STARTING';
  const isError = state === 'ERROR';
  const isActive = isOpen || isArmed || isExiting;
  const statusLabel = isOpen
    ? state === 'UNBALANCED' ? 'UNBALANCED' : 'ACTIVE (OPEN)'
    : isExiting
      ? 'EXITING'
      : isEntrySubmitted
        ? 'ENTRY SUBMITTED'
      : isArmed
        ? 'ARMED'
        : isStarting
          ? 'STARTING'
          : isError
            ? 'ERROR'
            : 'INACTIVE';

  return (
    <div className="card flex flex-col justify-between min-h-[130px] gap-2">
      {/* Top row: Heading + Status Badge */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-amber-500/10 flex items-center justify-center text-amber-400">
            <Zap className="w-4 h-4 fill-amber-400 text-amber-400" />
          </div>
          <span className="text-sm font-bold text-white tracking-tight">Straddle Strategy</span>
        </div>

        {/* Status Badge */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-[#12151A] border border-borderDark">
          <span
            className={`h-2 w-2 rounded-full ${
              isActive
                ? 'bg-[#20C978] shadow-[0_0_8px_#20C978]'
                : isError
                  ? 'bg-red-500'
                  : isStarting
                    ? 'bg-amber-400'
                    : 'bg-gray-500'
            }`}
          />
            <span className={isActive ? 'text-[#20C978]' : isError ? 'text-red-400' : 'text-gray-400'}>
              Status: {statusLabel}
          </span>
        </div>
      </div>

      {/* Middle row: Strategy description & Level 2 Risk tag */}
      <div className="flex items-center justify-between text-xs text-gray-400 font-normal">
        <span>Short call + short put · limited premium, substantial loss risk</span>
        <span className="text-[10px] text-[#20C978] font-semibold bg-[#1E2C22] px-1.5 py-0.5 rounded border border-[#20C978]/30">
          L2: TP {config?.tp_pct != null ? `${Number((config.tp_pct * 100).toFixed(1))}%` : '2%'} / SL {config?.sl_pct != null ? `${Number((config.sl_pct * 100).toFixed(1))}%` : '1%'}
        </span>
      </div>

      {/* Bottom row: Action Buttons */}
      <div className="flex items-center gap-3">
        {isOpen ? (
          <button
            onClick={onFlatten}
            disabled={loading}
            className="btn-red flex-1 py-2 text-xs font-bold uppercase tracking-wider"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            FLATTEN
          </button>
        ) : isExiting ? (
          <button
            onClick={onReset}
            disabled={loading}
            className="btn-red flex-1 py-2 text-xs font-bold uppercase tracking-wider bg-rose-600 hover:bg-rose-500 text-white flex items-center justify-center gap-1.5 shadow-md shadow-rose-900/30"
            title="Force Reset: Market-flatten open positions and return to QUOTING"
          >
            <RotateCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>FORCE RESET & RE-ARM</span>
          </button>
        ) : isArmed ? (
          <button
            onClick={onDisarm}
            disabled={loading}
            className="btn-red flex-1 py-2 text-xs font-bold uppercase tracking-wider bg-amber-600 hover:bg-amber-500"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            {isEntrySubmitted ? 'CANCEL ENTRY' : 'DISARM'}
          </button>
        ) : (
          <button
            onClick={onArm}
            disabled={loading || isStarting || isError}
            className="btn-green flex-1 py-2 text-xs font-bold uppercase tracking-wider text-black"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            ARM
          </button>
        )}

        <button
          onClick={onReset}
          disabled={loading}
          title="Emergency Reset: Cancel hanging orders, flatten open legs, and return to QUOTING"
          className="btn-outline px-3 py-2 text-xs font-semibold flex items-center gap-1 text-rose-400 hover:text-rose-300 hover:border-rose-500/50"
        >
          <RotateCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Reset</span>
        </button>

        <button
          onClick={onRefresh}
          title="Refresh market and strategy data"
          className="btn-outline px-3.5 py-2 text-xs font-semibold flex items-center gap-1.5 text-gray-300"
        >
          <RotateCw className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </button>
      </div>
      {actionError && (
        <div role="alert" className="flex items-center gap-1.5 text-xs text-red-400">
          <ShieldAlert className="w-3.5 h-3.5 shrink-0" />
          <span>{actionError}</span>
        </div>
      )}
      {(isStarting || isError) && statusMessage && (
        <div role={isError ? 'alert' : 'status'} className={`text-xs ${isError ? 'text-red-400' : 'text-amber-300'}`}>
          {statusMessage}
        </div>
      )}
      {latestEvent?.text && (
        <div role="status" className="flex gap-1.5 text-xs text-gray-400">
          <span className="shrink-0 font-semibold text-gray-300">
            {latestEvent.code || 'Strategy'}:
          </span>
          <span className="min-w-0 truncate">{latestEvent.text}</span>
        </div>
      )}
      {!latestEvent?.text && (
        <div role="status" className="text-xs text-gray-500">
          {statusFeedConnected
            ? 'Waiting for a current-run strategy event.'
            : 'Strategy status feed disconnected.'}
        </div>
      )}
    </div>
  );
}
