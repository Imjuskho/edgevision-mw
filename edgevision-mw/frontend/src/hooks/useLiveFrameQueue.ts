import { useCallback, useEffect, useState } from "react";
import { flushLiveFrameQueue, getLiveFramePendingCount, queueLiveFrame } from "./useOfflineSync";

export function useLiveFrameQueue() {
  const [pending, setPending] = useState(0);
  const [flushing, setFlushing] = useState(false);

  const refreshPending = useCallback(async () => {
    setPending(await getLiveFramePendingCount());
  }, []);

  const enqueue = useCallback(
    async (datasetId: string | undefined, blob: Blob, annotations: unknown[]) => {
      await queueLiveFrame(datasetId, blob, annotations);
      await refreshPending();
    },
    [refreshPending],
  );

  const flush = useCallback(async () => {
    if (!navigator.onLine) return 0;
    setFlushing(true);
    try {
      const count = await flushLiveFrameQueue();
      await refreshPending();
      return count;
    } finally {
      setFlushing(false);
    }
  }, [refreshPending]);

  useEffect(() => {
    void refreshPending();
  }, [refreshPending]);

  useEffect(() => {
    const onOnline = () => void flush();
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, [flush]);

  return { pending, flushing, enqueue, flush, refreshPending };
}
