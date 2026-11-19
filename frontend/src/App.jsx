import React, { useState, useEffect, useCallback } from 'react';
import useWebSocket from './hooks/useWebSocket';
import * as api from './services/api';
import Sidebar from './components/Sidebar';
import TopHeader from './components/TopHeader';
import BtcPriceCard from './components/BtcPriceCard';
import StraddleStrategyCard from './components/StraddleStrategyCard';
import MainPnlChart from './components/MainPnlChart';
import CurrentPnlCard from './components/CurrentPnlCard';
import OpenPositionsCard from './components/OpenPositionsCard';
import TradeHistoryCard from './components/TradeHistoryCard';
import SettingsModal from './components/SettingsModal';
import TradeHistoryModal from './components/TradeHistoryModal';
import AboutModal from './components/AboutModal';

export default function App() {
  const { snapshot, events, liveEvents, isConnected } = useWebSocket();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [marketData, setMarketData] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState('');

  // BTC reference price is also used by the ATM instrument selector.
  const fetchMarket = useCallback(async () => {
    try {
      const market = await api.getBtcMarket();
      if (market) {
        setMarketData(market);
      }
    } catch (e) {
      if (e instanceof Error) {
        setMarketData(null);
        console.warn('BTC reference price unavailable:', e.message);
      } else {
        setMarketData(null);
        console.warn('BTC reference price unavailable:', e);
      }
    }
  }, []);

  useEffect(() => {
    fetchMarket();
    const interval = setInterval(fetchMarket, 3500);
    return () => clearInterval(interval);
  }, [fetchMarket]);

  // Strategy commands
  const handleArm = useCallback(async () => {
    setActionLoading(true);
    setActionError('');
    try {
      await api.arm();
    } catch (err) {
      console.error('Failed to arm strategy:', err);
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setTimeout(() => setActionLoading(false), 600);
    }
  }, []);

  const handleDisarm = useCallback(async () => {
    setActionLoading(true);
    setActionError('');
    try {
      await api.disarm();
    } catch (err) {
      console.error('Failed to disarm strategy:', err);
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setTimeout(() => setActionLoading(false), 600);
    }
  }, []);

  const handleFlatten = useCallback(async () => {
    setActionLoading(true);
    setActionError('');
    try {
      await api.flatten();
    } catch (err) {
      console.error('Failed to flatten positions:', err);
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setTimeout(() => setActionLoading(false), 600);
    }
  }, []);

  const handleReset = useCallback(async () => {
    setActionLoading(true);
    setActionError('');
    try {
      await api.reset();
      fetchMarket();
    } catch (err) {
      console.error('Failed to reset strategy:', err);
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setTimeout(() => setActionLoading(false), 800);
    }
  }, [fetchMarket]);

  const handleUpdateConfig = useCallback(async (cfg) => {
    return await api.updateConfig(cfg);
  }, []);

  const handleRefresh = useCallback(() => {
    fetchMarket();
  }, [fetchMarket]);

  const state = snapshot?.state || 'IDLE';
  const environment = marketData?.environment || snapshot?.mode || 'demo';
  const latestStrategyEvent = liveEvents.length > 0
    ? liveEvents[liveEvents.length - 1]
    : null;

  return (
    <div className="min-h-screen bg-page text-gray-200 flex font-sans antialiased selection:bg-[#20C978]/30 selection:text-white">
      {/* Left Sidebar (fixed width matching reference ~15%) */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isConnected={isConnected}
        environment={environment}
      />

      {/* Main Content Area */}
      <main className="flex-1 min-w-0 p-5 lg:p-7 flex flex-col gap-5 max-w-[1550px]">
        <>
            {/* Top Header Bar */}
            <TopHeader
              isConnected={isConnected}
              environment={environment}
            />

            {/* Row 1: BTC Price Card & Straddle Strategy Card */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <BtcPriceCard marketData={marketData} />
              <StraddleStrategyCard
                state={state}
                config={snapshot?.config}
                onArm={handleArm}
                onDisarm={handleDisarm}
                onFlatten={handleFlatten}
                onReset={handleReset}
                onRefresh={handleRefresh}
                loading={actionLoading}
                actionError={actionError}
                latestEvent={latestStrategyEvent}
                statusFeedConnected={isConnected}
                statusMessage={snapshot?.node_message || ''}
              />
            </div>

            {/* Row 2: Middle Area (PnL Chart 65% + Current PnL & Positions 35%) */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
              {/* Main PnL Chart (approx 65% width) */}
              <div className="lg:col-span-8 flex flex-col">
                <MainPnlChart risk={snapshot?.risk} state={state} config={snapshot?.config} />
              </div>

              {/* Right Column: Stacked Current PnL & Open Positions (approx 35% width) */}
              <div className="lg:col-span-4 flex flex-col gap-4 justify-between">
                <CurrentPnlCard risk={snapshot?.risk} state={state} config={snapshot?.config} />
                <OpenPositionsCard
                  positions={snapshot?.positions}
                  quotes={snapshot?.quotes}
                  selection={snapshot?.selection}
                  btcPrice={marketData?.price}
                />
              </div>
            </div>

            {/* Current-run order and event history */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
              <div className="lg:col-span-12 flex flex-col">
                <TradeHistoryCard
                  orders={snapshot?.orders}
                  events={events}
                  onViewAll={() => setShowHistoryModal(true)}
                />
              </div>
            </div>
        </>
      </main>

      {/* Modals triggered from sidebar or cards */}
      {activeTab === 'settings' && (
        <SettingsModal
          snapshot={snapshot}
          onUpdateConfig={handleUpdateConfig}
          onClose={() => setActiveTab('dashboard')}
        />
      )}

      {(activeTab === 'history' || showHistoryModal) && (
        <TradeHistoryModal
          orders={snapshot?.orders}
          events={events}
          onClose={() => {
            setShowHistoryModal(false);
            if (activeTab === 'history') setActiveTab('dashboard');
          }}
        />
      )}

      {activeTab === 'about' && (
        <AboutModal environment={environment} onClose={() => setActiveTab('dashboard')} />
      )}
    </div>
  );
}
