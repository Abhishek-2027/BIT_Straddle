const BASE_URL = import.meta.env.VITE_API_URL || '';

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  try {
    const headers = new Headers(options.headers || {});
    if (options.body !== undefined && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    const res = await fetch(url, {
      ...options,
      headers,
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${body}`);
    }
    return await res.json();
  } catch (err) {
    console.error(`API error [${options.method || 'GET'} ${path}]:`, err);
    throw err;
  }
}

export function getState() {
  return request('/api/state');
}

export function arm() {
  return request('/api/arm', { method: 'POST' });
}

export function disarm() {
  return request('/api/disarm', { method: 'POST' });
}

export function flatten() {
  return request('/api/flatten', { method: 'POST' });
}

export function reset() {
  return request('/api/reset', { method: 'POST' });
}

export function updateConfig(config) {
  return request('/api/config', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export function getEvents(since, limit = 100) {
  const params = new URLSearchParams();
  if (since) params.set('since', since);
  if (limit) params.set('limit', String(limit));
  return request(`/api/events?${params}`);
}

export function getOrders() {
  return request('/api/orders');
}

export function healthCheck() {
  return request('/api/health');
}

export function getBtcMarket() {
  return request('/api/market/btc');
}
