import { useEffect } from "react";
import { Layers } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { useBatchInference, type BatchInferenceMode } from "../hooks/useBatchInference";

interface BatchInferenceActionProps {
  mode: BatchInferenceMode;
  datasetId: string;
  disabled?: boolean;
  onComplete?: (summary: Record<string, unknown>) => void;
  onError?: (message: string) => void;
}

export function BatchInferenceAction({
  mode,
  datasetId,
  disabled = false,
  onComplete,
  onError,
}: BatchInferenceActionProps) {
  const { t } = useTranslation();
  const { isRunning, progress, status, error, result, startBatch } = useBatchInference(mode);

  useEffect(() => {
    if (status === "COMPLETED" && result) {
      onComplete?.(result);
    }
  }, [status, result, onComplete]);

  useEffect(() => {
    if (error) {
      onError?.(error);
    }
  }, [error, onError]);

  const progressLabel =
    progress && progress.total > 0
      ? t("batchInference.progress", {
          current: progress.current ?? progress.processed,
          total: progress.total,
        })
      : null;

  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        icon={<Layers size={14} />}
        onClick={() => void startBatch(datasetId, "remaining")}
        disabled={disabled || isRunning || !datasetId}
        loading={isRunning}
      >
        {mode === "road"
          ? t("batchInference.inferRemainingRoad")
          : t("batchInference.inferRemaining")}
      </Button>

      {isRunning && (
        <Badge variant="info">
          {progressLabel ?? t("batchInference.running")}
        </Badge>
      )}

      {status === "COMPLETED" && result && (
        <Badge variant="success">
          {t("batchInference.complete", {
            processed: (result.processed as number) ?? 0,
          })}
        </Badge>
      )}

      {error && <Badge variant="danger">{error}</Badge>}
    </>
  );
}
