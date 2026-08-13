import { useCallback } from "react";
import { useToast } from "../components/Toast";
import { studioApi } from "../services/api";
import { useOfflineSync } from "./useOfflineSync";

export function isOfflineError(err: unknown): boolean {
  if (!navigator.onLine) return true;
  const e = err as { code?: string; message?: string; response?: { status?: number } };
  if (
    e.code === "ERR_NETWORK" ||
    e.code === "ECONNABORTED" ||
    e.code === "ETIMEDOUT" ||
    e.message === "Network Error" ||
    e.message?.includes("timeout")
  ) {
    return true;
  }
  const status = e.response?.status;
  return status === 503 || status === 504;
}

export function useResilientSave(sessionId: string) {
  const { queueAction, triggerSync } = useOfflineSync(sessionId);
  const { showToast } = useToast();

  const saveBboxAnnotations = useCallback(
    async (
      imageId: string,
      imageIndex: number,
      annotations: Parameters<typeof studioApi.saveAnnotation>[2],
      toolUsed = "bbox",
    ): Promise<{ queued: boolean }> => {
      const payload = {
        session_id: sessionId,
        image_index: imageIndex,
        annotations,
        tool_used: toolUsed,
      };

      try {
        await studioApi.saveAnnotation(sessionId, imageIndex, annotations, toolUsed);
        return { queued: false };
      } catch (err) {
        if (!isOfflineError(err)) throw err;
        await queueAction(imageId, "edit", payload);
        void triggerSync();
        showToast("Saved offline — will sync when connection returns", "info");
        return { queued: true };
      }
    },
    [sessionId, queueAction, triggerSync, showToast],
  );

  const saveRoadAnnotations = useCallback(
    async (
      imageId: string,
      imageIndex: number,
      annotations: unknown[],
      toolUsed = "polygon",
    ): Promise<{ queued: boolean }> => {
      const payload = {
        session_id: sessionId,
        image_index: imageIndex,
        annotations,
        tool_used: toolUsed,
      };

      try {
        await studioApi.saveRoadAnnotations(sessionId, imageIndex, annotations, toolUsed);
        return { queued: false };
      } catch (err) {
        if (!isOfflineError(err)) throw err;
        await queueAction(imageId, "edit", payload);
        void triggerSync();
        showToast("Saved offline — will sync when connection returns", "info");
        return { queued: true };
      }
    },
    [sessionId, queueAction, triggerSync, showToast],
  );

  return { saveBboxAnnotations, saveRoadAnnotations };
}
