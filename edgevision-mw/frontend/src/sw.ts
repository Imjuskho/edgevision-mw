// src/sw.ts
// EdgeVision Studio Service Worker: offline caching, background sync, model updates

/// <reference lib="webworker" />

import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { StaleWhileRevalidate, CacheFirst, NetworkFirst } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';
import { BackgroundSyncPlugin } from 'workbox-background-sync';

declare const self: ServiceWorkerGlobalScope;

interface PeriodicSyncEvent extends Event {
  tag: string;
  waitUntil(f: Promise<void>): void;
}

// Precache manifest injected by vite-plugin-pwa
cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);

// ─── Lifecycle: force immediate activation + notify clients ───

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          .filter((name) => name.startsWith('studio-assets') || name.startsWith('workbox-precache'))
          .map((name) => caches.delete(name))
      )
    ).then(() => self.clients.claim())
  );
});

// ─── Cache Strategies ───

// API responses: Network first, cache fallback (stale data better than no data)
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/v1/studio/'),
  new NetworkFirst({
    cacheName: 'studio-api-v1',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 500,
        maxAgeSeconds: 7 * 24 * 60 * 60, // 7 days
      }),
    ],
  })
);

// Images from MinIO: Cache first, network fallback
registerRoute(
  ({ url }) => url.pathname.includes('/studio/images/'),
  new CacheFirst({
    cacheName: 'studio-images',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 1000,
        maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
      }),
    ],
  })
);

// ONNX models: Cache first, long expiry
registerRoute(
  ({ url }) => url.pathname.endsWith('.onnx'),
  new CacheFirst({
    cacheName: 'studio-models',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 10,
        maxAgeSeconds: 90 * 24 * 60 * 60, // 90 days
      }),
    ],
  })
);

// Static assets: Network first (avoids serving stale cached JS/CSS)
registerRoute(
  ({ request }) => ['style', 'script', 'worker'].includes(request.destination),
  new NetworkFirst({
    cacheName: 'studio-assets',
  })
);

// ─── Background Sync ───

const bgSyncPlugin = new BackgroundSyncPlugin('studio-sync-queue', {
  maxRetentionTime: 24 * 60, // 24 hours (in minutes)
  onSync: async ({ queue }) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let entry: any;
    while ((entry = await queue.shiftRequest())) {
      try {
        await fetch(entry.request);
        // Notify clients
        const clients = await self.clients.matchAll({ type: 'window' });
        clients.forEach(client => {
          client.postMessage({ type: 'SYNC_SUCCESS', url: entry.request.url });
        });
      } catch (error) {
        await queue.unshiftRequest(entry);
        throw error;
      }
    }
  },
});

// Register background sync for annotation saves
registerRoute(
  ({ url }) => url.pathname === '/api/v1/studio/annotations/save',
  new NetworkFirst({
    plugins: [bgSyncPlugin],
  }),
  'POST'
);

// ─── Push Notifications (optional) ───

self.addEventListener('push', (event) => {
  const data = event.data?.json() ?? {};
  event.waitUntil(
    self.registration.showNotification(data.title ?? 'EdgeVision', {
      body: data.body ?? 'New notification',
      icon: '/icon-192x192.png',
      badge: '/badge-72x72.png',
      tag: data.tag ?? 'default',
      requireInteraction: data.requireInteraction ?? false,
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.openWindow('/studio')
  );
});

// ─── Message Handling (from main thread) ───

self.addEventListener('message', (event) => {
  if (event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data.type === 'CACHE_MODELS') {
    // Pre-cache ONNX models on demand
    const models = event.data.models as string[];
    caches.open('studio-models').then(cache => {
      models.forEach(url => cache.add(url));
    });
  }
});

// ─── Periodic Background Sync (for model updates) ───

self.addEventListener('periodicsync' as unknown as string, (event: Event) => {
  const evt = event as unknown as PeriodicSyncEvent;
  if (evt.tag === 'model-update-check') {
    evt.waitUntil(checkModelUpdates());
  }
});

async function checkModelUpdates() {
  try {
    const response = await fetch('/api/v1/studio/models/manifest.json');
    const manifest = await response.json();
    const cache = await caches.open('studio-models');

    for (const model of manifest.models) {
      const cached = await cache.match(model.url);
      if (!cached) {
        // New model version available
        await cache.add(model.url);
        // Notify clients
        const clients = await self.clients.matchAll();
        clients.forEach(client => {
          client.postMessage({
            type: 'MODEL_UPDATED',
            modelName: model.name,
            version: model.version,
          });
        });
      }
    }
  } catch (e) {
    console.error('Model update check failed:', e);
  }
}
