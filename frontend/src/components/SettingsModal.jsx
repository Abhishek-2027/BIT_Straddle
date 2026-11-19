import React, { useState } from 'react';
import { X, Save, Shield, Sliders } from 'lucide-react';

export default function SettingsModal({ snapshot, onUpdateConfig, onClose }) {
  const currentCfg = snapshot?.config || {};
  const [slPct, setSlPct] = useState(currentCfg.sl_pct ? (currentCfg.sl_pct * 100).toFixed(1) : '1.0');
  const [tpPct, setTpPct] = useState(currentCfg.tp_pct ? (currentCfg.tp_pct * 100).toFixed(1) : '2.0');
  const [qty, setQty] = useState(currentCfg.qty ? String(currentCfg.qty) : '0.01');
  const [maxSpread, setMaxSpread] = useState(currentCfg.max_spread_pct ? (currentCfg.max_spread_pct * 100).toFixed(1) : '1.5');
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState('');

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSavedMsg('');
    try {
      await onUpdateConfig({
        sl_pct: parseFloat(slPct) / 100,
        tp_pct: parseFloat(tpPct) / 100,
        qty: parseFloat(qty),
        max_spread_pct: parseFloat(maxSpread) / 100,
      });
      setSavedMsg('Settings saved successfully!');
      setTimeout(() => setSavedMsg(''), 3000);
    } catch (err) {
      console.error(err);
      setSavedMsg('Failed to update settings');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#171B21] border border-borderDark rounded-2xl w-full max-w-md p-6 shadow-2xl relative">
        <div className="flex items-center justify-between pb-4 border-b border-borderDark/60">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#20C978]/10 flex items-center justify-center text-[#20C978]">
              <Sliders className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Strategy Settings</h2>
              <p className="text-xs text-gray-400">Configure risk and sizing parameters</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-lg hover:bg-borderDark flex items-center justify-center text-gray-400 hover:text-white"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSave} className="flex flex-col gap-4 mt-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-gray-400 block mb-1">Stop-Loss (%)</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={slPct}
                onChange={(e) => setSlPct(e.target.value)}
                className="w-full bg-[#12151A] border border-borderDark rounded-xl px-3 py-2 text-sm text-white font-medium focus:outline-none focus:border-[#20C978]"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-400 block mb-1">Take-Profit (%)</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={tpPct}
                onChange={(e) => setTpPct(e.target.value)}
                className="w-full bg-[#12151A] border border-borderDark rounded-xl px-3 py-2 text-sm text-white font-medium focus:outline-none focus:border-[#20C978]"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-gray-400 block mb-1">Quantity (BTC)</label>
              <input
                type="number"
                step="0.001"
                min="0.001"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
                className="w-full bg-[#12151A] border border-borderDark rounded-xl px-3 py-2 text-sm text-white font-medium focus:outline-none focus:border-[#20C978]"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-400 block mb-1">Max Spread (%)</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={maxSpread}
                onChange={(e) => setMaxSpread(e.target.value)}
                className="w-full bg-[#12151A] border border-borderDark rounded-xl px-3 py-2 text-sm text-white font-medium focus:outline-none focus:border-[#20C978]"
              />
            </div>
          </div>

          <div className="bg-[#12151A] border border-borderDark rounded-xl p-3 text-xs text-gray-400 flex items-start gap-2.5">
            <Shield className="w-4 h-4 text-[#20C978] shrink-0 mt-0.5" />
            <span>Connected to Bybit Demo Trading UTA. Real orders are submitted with automated SL/TP risk tracking.</span>
          </div>

          {savedMsg && (
            <div className={`text-xs font-semibold text-center ${savedMsg.includes('Failed') ? 'text-red-400' : 'text-[#20C978]'}`}>
              {savedMsg}
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-borderDark/60">
            <button
              type="button"
              onClick={onClose}
              className="btn-outline px-4 py-2 text-xs font-semibold"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="btn-green px-5 py-2 text-xs font-bold flex items-center gap-1.5"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{saving ? 'Saving...' : 'Save Settings'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
