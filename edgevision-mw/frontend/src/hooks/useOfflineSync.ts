// IndexedDB sync queue with conflict resolution and background retry

import { useEffect, useCallback, useState } from "react";
import Dexie, { type Table } from "dexie";
import { studioApi } from "../services/api";

interface SyncQueueEntry {
  id?: number;
  imageId: string;
  sessionId: string;
  actionType: "create" | "edit" | "delete" | "approve" | "reject";
  payload: unknown;
  status: "pending" | "syncing" | "failed" | "resolved" | "duplicate_checksum";
  retryCount: number;
  lastError?: string;
  createdAt: Date;
  etag?: string;
  nextRetryAt?: Date;
}

interface LiveFrameQueueEntry {
  id?: number;
  datasetId?: string;
  blob: Blob;
  annotations: string;
  orientation?: string;
  masks?: string;
  bbox_3d?: string;
  checksum?: string;
  status: "pending" | "syncing" | "failed" | "resolved" | "duplicate_checksum";
  retryCount: number;
  lastError?: string;
  createdAt: Date;
  nextRetryAt?: Date;
}

interface SyncStats {
  pending: number;
  syncing: number;
  failed: number;
  resolved: number;
  livePending: number;
  liveFailed: number;
}

class StudioDatabase extends Dexie {
  syncQueue!: Table<SyncQueueEntry>;
  imageCache!: Table<{ imageId: string; blob: Blob; thumbnailBlob: Blob; nodeId: string; captureTime: Date }>;
  annotationDrafts!: Table<{ id?: number; imageId: string; sessionId: string; data: unknown; modifiedAt: Date }>;
  prelabelCache!: Table<{ imageId: string; modelVersion: string; annotations: unknown; computedAt: Date }>;
  modelCache!: Table<{ modelName: string; version: string; blob: Blob; sizeBytes: number }>;
  liveFrameQueue!: Table<LiveFrameQueueEntry>;

  constructor() {
    super("EdgeVisionStudio");
    this.version(1).stores({
      syncQueue: "++id, imageId, sessionId, status, retryCount, createdAt",
      imageCache: "imageId, nodeId, captureTime",
      annotationDrafts: "++id, imageId, sessionId, modifiedAt",
      prelabelCache: "imageId, modelVersion, computedAt",
      modelCache: "modelName, version",
    });
    this.version(2).stores({
      syncQueue: "++id, imageId, sessionId, status, retryCount, createdAt",
      imageCache: "imageId, nodeId, captureTime",
      annotationDrafts: "++id, imageId, sessionId, modifiedAt",
      prelabelCache: "imageId, modelVersion, computedAt",
      modelCache: "modelName, version",
      liveFrameQueue: "++id, status, datasetId, retryCount, createdAt",
    });
    this.version(3).stores({
      syncQueue: "++id, imageId, sessionId, status, retryCount, createdAt, nextRetryAt",
      imageCache: "imageId, nodeId, captureTime",
      annotationDrafts: "++id, imageId, sessionId, modifiedAt",
      prelabelCache: "imageId, modelVersion, computedAt",
      modelCache: "modelName, version",
      liveFrameQueue: "++id, status, datasetId, retryCount, createdAt, checksum, nextRetryAt",
    });
  }
}

const db = new StudioDatabase();
export const MAX_RETRIES = 6;
const MAX_LIVE_FRAME_ENTRIES = 50;
const MAX_LIVE_FRAME_BYTES = 100 * 1024 * 1024;
const syncLocks = new Map<string, boolean>();

/** Compute exponential backoff delay with jitter (ms). Cap at ~60s. */
export function computeBackoffMs(retryCount: number, retryAfterSec?: number): number {
  if (retryAfterSec && retryAfterSec > 0) {
    return retryAfterSec * 1000 + Math.floor(Math.random() * 500);
  }
  const base = Math.min(60_000, 1000 * 2 ** retryCount);
  const jitter = Math.floor(Math.random() * base * 0.25);
  return base + jitter;
}

/** SHA-256 hex digest of a Blob (browser crypto). */
export async function sha256Hex(blob: Blob): Promise<string> {
  const buffer = await blob.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** True when entry is ready for retry (respects nextRetryAt). */
export function isReadyForRetry(entry: { retryCount: number; nextRetryAt?: Date }, now = Date.now()): boolean {
  if (entry.retryCount >= MAX_RETRIES) return false;
  if (!entry.nextRetryAt) return true;
  return entry.nextRetryAt.getTime() <= now;
}

async function updateGlobalStats(): Promise<SyncStats> {
  const pending = await db.syncQueue.where("status").equals("pending").count();
  const syncing = await db.syncQueue.where("status").equals("syncing").count();
  const failed = await db.syncQueue.where("status").equals("failed").count();
  const resolved = await db.syncQueue.where("status").equals("resolved").count();
  const livePending = await db.liveFrameQueue
    .filter((e) => e.status === "pending" && isReadyForRetry(e))
    .count();
  const liveFailed = await db.liveFrameQueue.where("status").equals("failed").count();
  return { pending, syncing, failed, resolved, livePending, liveFailed };
}

/** Pending or failed queue entries for a specific session. */
export async function getPendingSyncCount(sessionId: string): Promise<number> {
  const entries = await db.syncQueue.where("sessionId").equals(sessionId).toArray();
  return entries.filter(
    (e) => (e.status === "pending" || e.status === "failed") && isReadyForRetry(e),
  ).length;
}

/** Flush queued actions for one session (survives route changes; keyed by sessionId). */
export async function flushSessionSync(sessionId: string): Promise<void> {
  if (!navigator.onLine || !sessionId || syncLocks.get(sessionId)) return;
  syncLocks.set(sessionId, true);

  try {
    const pending = await db.syncQueue
      .where("sessionId")
      .equals(sessionId)
      .filter(
        (item) =>
          (item.status === "pending" || item.status === "failed") && isReadyForRetry(item),
      )
      .toArray();

    if (pending.length === 0) return;

    const batch = pending.slice(0, 50);
    for (const entry of batch) {
      await db.syncQueue.update(entry.id!, { status: "syncing" });
    }

    try {
      const ifMatchHeader = batch.map((e) => e.etag).filter(Boolean).join(",") || "*";
      const response = await studioApi.syncBatch(
        sessionId,
        batch.map((e) => ({
          image_id: e.imageId,
          action_type: e.actionType,
          payload: e.payload,
        })),
        ifMatchHeader,
      );

      const result = response.data;
      for (const entry of batch) {
        await db.syncQueue.update(entry.id!, { status: "resolved" });
      }

      if (result.conflicts?.length) {
        for (const conflict of result.conflicts) {
          const entry = batch.find((e) => e.imageId === conflict.image_id);
          if (entry && conflict.resolution === "server_wins") {
            await db.annotationDrafts.where({ imageId: conflict.image_id }).delete();
          }
        }
      }
    } catch (error) {
      const resp = (error as { response?: { status?: number; headers?: Record<string, string> } })?.response;
      const statusCode = resp?.status;
      const retryAfter = parseInt(resp?.headers?.["retry-after"] ?? "0", 10);
      for (const entry of batch) {
        if (statusCode === 409) {
          await db.syncQueue.update(entry.id!, {
            status: "failed",
            lastError: "Conflict: server state changed",
            retryCount: entry.retryCount + 1,
            nextRetryAt: new Date(Date.now() + computeBackoffMs(entry.retryCount + 1, retryAfter)),
          });
        } else {
          const newRetry = entry.retryCount + 1;
          await db.syncQueue.update(entry.id!, {
            status: newRetry >= MAX_RETRIES ? "failed" : "pending",
            retryCount: newRetry,
            lastError: error instanceof Error ? error.message : "Sync failed",
            nextRetryAt: new Date(Date.now() + computeBackoffMs(newRetry, retryAfter)),
          });
        }
      }
    }
  } finally {
    syncLocks.delete(sessionId);
  }
}

/** Flush queued actions for every session with pending or retryable failed entries. */
export async function flushAllPendingSessions(): Promise<void> {
  if (!navigator.onLine) return;

  const entries = await db.syncQueue
    .filter(
      (item) =>
        (item.status === "pending" || item.status === "failed") && isReadyForRetry(item),
    )
    .toArray();

  const sessionIds = [...new Set(entries.map((e) => e.sessionId).filter(Boolean))];
  for (const sid of sessionIds) {
    await flushSessionSync(sid);
  }

  await flushLiveFrameQueue();
}

export async function getLiveFramePendingCount(): Promise<number> {
  return db.liveFrameQueue
    .filter(
      (e) =>
        (e.status === "pending" || e.status === "failed") &&
        isReadyForRetry(e),
    )
    .count();
}

export async function queueLiveFrame(
  datasetId: string | undefined,
  blob: Blob,
  annotations: unknown[],
  orientation = "normal",
  masks?: unknown[],
  bbox_3d?: unknown[],
): Promise<void> {
  const checksum = await sha256Hex(blob);
  await enforceLiveFrameQueueLimits(blob.size);

  await db.liveFrameQueue.add({
    datasetId,
    blob,
    annotations: JSON.stringify(annotations),
    orientation,
    masks: masks ? JSON.stringify(masks) : undefined,
    bbox_3d: bbox_3d ? JSON.stringify(bbox_3d) : undefined,
    checksum,
    status: "pending",
    retryCount: 0,
    createdAt: new Date(),
  });
}

async function enforceLiveFrameQueueLimits(incomingBytes: number): Promise<void> {
  const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  await db.liveFrameQueue
    .where("status")
    .equals("resolved")
    .filter((e) => e.createdAt < weekAgo)
    .delete();

  let entries = await db.liveFrameQueue.orderBy("createdAt").toArray();
  let totalBytes = entries.reduce((sum, e) => sum + e.blob.size, 0) + incomingBytes;

  while (
    entries.length >= MAX_LIVE_FRAME_ENTRIES ||
    totalBytes > MAX_LIVE_FRAME_BYTES
  ) {
    const evict =
      entries.find((e) => e.status === "resolved") ??
      entries.find((e) => e.status === "duplicate_checksum") ??
      entries.find((e) => e.status === "failed") ??
      null;
    if (!evict?.id) break;
    totalBytes -= evict.blob.size;
    await db.liveFrameQueue.delete(evict.id);
    entries = entries.filter((e) => e.id !== evict.id);
  }
}

async function fetchServerChecksums(token: string): Promise<Set<string>> {
  try {
    const resp = await fetch("/api/v1/annotations/live/checksums", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) return new Set();
    const data = await resp.json();
    return new Set((data.checksums as string[]) ?? []);
  } catch {
    return new Set();
  }
}

/** Upload queued live-annotate frames when online. */
export async function flushLiveFrameQueue(): Promise<number> {
  if (!navigator.onLine) return 0;

  const token = localStorage.getItem("studio_token");
  if (!token) return 0;

  const serverChecksums = await fetchServerChecksums(token);

  const pending = await db.liveFrameQueue
    .filter(
      (e) =>
        (e.status === "pending" || e.status === "failed") &&
        isReadyForRetry(e),
    )
    .toArray();

  let flushed = 0;
  for (const entry of pending) {
    if (entry.checksum && serverChecksums.has(entry.checksum)) {
      await db.liveFrameQueue.update(entry.id!, {
        status: "duplicate_checksum",
        lastError: "Already uploaded (checksum match)",
      });
      continue;
    }

    await db.liveFrameQueue.update(entry.id!, { status: "syncing" });
    try {
      const formData = new FormData();
      formData.append("file", entry.blob, `live_${entry.createdAt.getTime()}.jpg`);
      formData.append("annotations", entry.annotations);
      if (entry.orientation) formData.append("orientation", entry.orientation);
      if (entry.masks) formData.append("masks", entry.masks);
      if (entry.bbox_3d) formData.append("bbox_3d", entry.bbox_3d);
      if (entry.datasetId) formData.append("dataset_id", entry.datasetId);

      const resp = await fetch("/api/v1/annotations/live", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!resp.ok) {
        const retryAfter = parseInt(resp.headers.get("retry-after") ?? "0", 10);
        const err = await resp.json().catch(() => ({ detail: "Save failed" }));
        const newRetry = entry.retryCount + 1;
        await db.liveFrameQueue.update(entry.id!, {
          status: newRetry >= MAX_RETRIES ? "failed" : "pending",
          retryCount: newRetry,
          lastError: typeof err.detail === "string" ? err.detail : "Save failed",
          nextRetryAt: new Date(Date.now() + computeBackoffMs(newRetry, retryAfter)),
        });
        continue;
      }
      await db.liveFrameQueue.update(entry.id!, { status: "resolved" });
      flushed++;
    } catch (error) {
      const newRetry = entry.retryCount + 1;
      await db.liveFrameQueue.update(entry.id!, {
        status: newRetry >= MAX_RETRIES ? "failed" : "pending",
        retryCount: newRetry,
        lastError: error instanceof Error ? error.message : "Upload failed",
        nextRetryAt: new Date(Date.now() + computeBackoffMs(newRetry)),
      });
    }
  }
  return flushed;
}

export function useOfflineSync(sessionId: string) {
  const [stats, setStats] = useState<SyncStats>({
    pending: 0,
    syncing: 0,
    failed: 0,
    resolved: 0,
    livePending: 0,
    liveFailed: 0,
  });
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  const refreshStats = useCallback(async () => {
    setStats(await updateGlobalStats());
  }, []);

  const triggerSync = useCallback(async () => {
    await flushAllPendingSessions();
    await refreshStats();
  }, [refreshStats]);

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      void triggerSync();
    };
    const handleOffline = () => setIsOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [triggerSync]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next = await updateGlobalStats();
      if (!cancelled) setStats(next);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isOnline || !sessionId) return;
    const interval = setInterval(() => void triggerSync(), 30000);
    return () => clearInterval(interval);
  }, [isOnline, sessionId, triggerSync]);

  const queueAction = useCallback(
    async (
      imageId: string,
      actionType: SyncQueueEntry["actionType"],
      payload: unknown,
      etag?: string,
    ) => {
      await db.syncQueue.add({
        imageId,
        sessionId,
        actionType,
        payload,
        status: "pending",
        retryCount: 0,
        createdAt: new Date(),
        etag,
      });
      await refreshStats();
      if (navigator.onLine) void triggerSync();
    },
    [sessionId, refreshStats, triggerSync],
  );

  const clearResolved = useCallback(async () => {
    await db.syncQueue.where("status").equals("resolved").delete();
    await refreshStats();
  }, [refreshStats]);

  const retryFailed = useCallback(async () => {
    if (!sessionId) return;
    await db.syncQueue
      .where("sessionId")
      .equals(sessionId)
      .filter((e) => e.status === "failed")
      .modify({ status: "pending", retryCount: 0, nextRetryAt: undefined });
    await refreshStats();
    if (navigator.onLine) void triggerSync();
  }, [sessionId, refreshStats, triggerSync]);

  const cacheImage = useCallback(
    async (imageId: string, imageBlob: Blob, thumbnailBlob: Blob, nodeId: string, captureTime: Date) => {
      await db.imageCache.put({ imageId, blob: imageBlob, thumbnailBlob, nodeId, captureTime });
    },
    [],
  );

  const getCachedImage = useCallback(async (imageId: string) => db.imageCache.get(imageId), []);

  const cachePrelabels = useCallback(async (imageId: string, modelVersion: string, annotations: unknown) => {
    await db.prelabelCache.put({ imageId, modelVersion, annotations, computedAt: new Date() });
  }, []);

  const getCachedPrelabels = useCallback(async (imageId: string) => {
    const cached = await db.prelabelCache.get(imageId);
    if (cached && Date.now() - cached.computedAt.getTime() < 7 * 24 * 60 * 60 * 1000) {
      return cached.annotations;
    }
    return null;
  }, []);

  return {
    isOnline,
    stats,
    queueAction,
    triggerSync,
    clearResolved,
    retryFailed,
    cacheImage,
    getCachedImage,
    cachePrelabels,
    getCachedPrelabels,
  };
}
