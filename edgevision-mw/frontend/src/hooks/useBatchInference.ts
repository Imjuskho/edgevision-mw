import { useCallback, useEffect, useRef, useState } from "react";
import { studioApi } from "../services/api";
import type { BatchJobStatusResponse } from "../types";

export type BatchInferenceMode = "detection" | "road";

interface BatchProgress {
  processed: number;
  failed: number;
  skipped: number;
  total: number;
  current: number;
}

interface UseBatchInferenceReturn {
  isRunning: boolean;
  jobId: string | null;
  progress: BatchProgress | null;
  status: BatchJobStatusResponse["status"] | null;
  error: string | null;
  result: Record<string, unknown> | null;
  startBatch: (datasetId: string, scope?: "remaining" | "all") => Promise<void>;
  reset: () => void;
}

const POLL_MS = 2000;

export function useBatchInference(mode: BatchInferenceMode): UseBatchInferenceReturn {
  const [isRunning, setIsRunning] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState<BatchProgress | null>(null);
  const [status, setStatus] = useState<BatchJobStatusResponse["status"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    clearPoll();
    setIsRunning(false);
    setJobId(null);
    setProgress(null);
    setStatus(null);
    setError(null);
    setResult(null);
  }, [clearPoll]);

  const pollJob = useCallback(
    (id: string) => {
      clearPoll();
      pollRef.current = setInterval(async () => {
        try {
          const resp = await studioApi.getBatchJobStatus(id);
          const data = resp.data as BatchJobStatusResponse;
          setStatus(data.status);

          if (data.progress) {
            setProgress(data.progress as BatchProgress);
          }

          if (data.status === "COMPLETED") {
            clearPoll();
            setIsRunning(false);
            setResult(data.result ?? null);
          } else if (data.status === "FAILED") {
            clearPoll();
            setIsRunning(false);
            setError(data.error ?? "Batch job failed");
          }
        } catch (err) {
          clearPoll();
          setIsRunning(false);
          setError(err instanceof Error ? err.message : "Failed to poll job status");
        }
      }, POLL_MS);
    },
    [clearPoll],
  );

  const startBatch = useCallback(
    async (datasetId: string, scope: "remaining" | "all" = "remaining") => {
      reset();
      setIsRunning(true);
      setError(null);

      try {
        const resp =
          mode === "road"
            ? await studioApi.segmentRoadDatasetBatch(datasetId, { scope })
            : await studioApi.prelabelDatasetBatch(datasetId, { scope });

        const data = resp.data as { job_id: string; total_images: number };
        setJobId(data.job_id);
        setProgress({
          processed: 0,
          failed: 0,
          skipped: 0,
          total: data.total_images,
          current: 0,
        });
        setStatus("PENDING");
        pollJob(data.job_id);
      } catch (err) {
        setIsRunning(false);
        const axiosDetail =
          typeof err === "object" &&
          err !== null &&
          "response" in err &&
          typeof (err as { response?: { data?: { detail?: unknown } } }).response?.data
            ?.detail === "string"
            ? (err as { response: { data: { detail: string } } }).response.data.detail
            : null;
        setError(axiosDetail ?? (err instanceof Error ? err.message : "Failed to start batch job"));
      }
    },
    [mode, pollJob, reset],
  );

  useEffect(() => () => clearPoll(), [clearPoll]);

  return {
    isRunning,
    jobId,
    progress,
    status,
    error,
    result,
    startBatch,
    reset,
  };
}
