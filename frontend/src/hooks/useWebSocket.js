import { useState, useEffect, useRef, useCallback } from 'react';

const MAX_EVENTS = 200;
const MAX_RECONNECT_DELAY = 30000;

function mergeEvents(current, incoming) {
  const unique = new Map();
  for (const event of [...current, ...incoming]) {
    const identity = event.timestamp
      ? `${event.timestamp}|${event.seq ?? ''}|${event.code || ''}|${event.text || ''}`
      : `seq:${event.seq ?? ''}|${event.code || ''}|${event.text || ''}`;
    unique.set(identity, event);
  }

  return [...unique.values()]
    .sort((a, b) => {
      const aTime = Date.parse(a.timestamp || '');
      const bTime = Date.parse(b.timestamp || '');
      return (Number.isNaN(aTime) ? 0 : aTime) - (Number.isNaN(bTime) ? 0 : bTime);
    })
    .slice(-MAX_EVENTS);
}

export default function useWebSocket() {
  const [snapshot, setSnapshot] = useState(null);
  const [events, setEvents] = useState([]);
  const [liveEvents, setLiveEvents] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [reconnectCount, setReconnectCount] = useState(0);

  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const reconnectDelay = useRef(1000);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = import.meta.env.VITE_WS_URL || `${wsProtocol}//${window.location.host}/ws`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setIsConnected(true);
      reconnectDelay.current = 1000; // reset backoff
      console.log('[WS] Connected');
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(event.data);

        if (msg.type === 'snapshot') {
          setSnapshot(msg);
        } else if (msg.type === 'event') {
          setEvents((prev) => mergeEvents(prev, [msg]));
          setLiveEvents((prev) => mergeEvents(prev, [msg]));
        }
      } catch (err) {
        console.error('[WS] Parse error:', err);
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setIsConnected(false);
      console.log(`[WS] Disconnected. Reconnecting in ${reconnectDelay.current}ms...`);

      reconnectTimer.current = setTimeout(() => {
        setReconnectCount((c) => c + 1);
        connect();
      }, reconnectDelay.current);

      // Exponential backoff: 1s, 2s, 4s, 8s, ... max 30s
      reconnectDelay.current = Math.min(reconnectDelay.current * 2, MAX_RECONNECT_DELAY);
    };

    ws.onerror = (err) => {
      console.error('[WS] Error:', err);
      ws.close();
    };
  }, []);

  useEffect(() => {
    mountedRef.current = true;

    // Fetch initial state and events via REST immediately for instant hydration
    const baseUrl = import.meta.env.VITE_API_URL || '';
    fetch(`${baseUrl}/api/state`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (mountedRef.current && data) {
          setSnapshot((prev) => prev || data);
        }
      })
      .catch((err) => console.debug('[WS] Initial state fetch notice:', err));

    fetch(`${baseUrl}/api/events`)
      .then((res) => (res.ok ? res.json() : []))
      .then((evList) => {
        if (mountedRef.current && Array.isArray(evList) && evList.length > 0) {
          setEvents((prev) => mergeEvents(prev, evList));
        }
      })
      .catch((err) => console.debug('[WS] Initial events fetch notice:', err));

    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        if (wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.close();
        }
      }
    };
  }, [connect]);

  const sendCommand = useCallback(async (command, body) => {
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const res = await fetch(`${baseUrl}/api/${command}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status}: ${text}`);
    }
    return res.json();
  }, []);

  return { snapshot, events, liveEvents, isConnected, reconnectCount, sendCommand };
}
