import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { studioApi } from "../services/api";
import { LoadingOverlay } from "../components/Spinner";

interface SessionGateProps {
  onSessionReady: (sessionId: string, datasetId: string) => void;
  children: (ctx: { sessionId: string; datasetId: string }) => ReactNode;
}

/**
 * Ensures an annotation session exists for the :datasetId route param before
 * rendering children. Handles deep links, refresh, and dataset switches.
 */
export function SessionGate({ onSessionReady, children }: SessionGateProps) {
  const { t } = useTranslation();
  const { datasetId: rawDatasetId } = useParams<{ datasetId: string }>();
  const datasetId = rawDatasetId ? decodeURIComponent(rawDatasetId) : "";
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!datasetId) {
      setSessionId(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(false);
    setSessionId(null);

    (async () => {
      try {
        const resp = await studioApi.createSession(datasetId);
        if (cancelled) return;
        const id = resp.data.id;
        setSessionId(id);
        onSessionReady(id, datasetId);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [datasetId, onSessionReady]);

  if (!datasetId) return null;
  if (loading) return <LoadingOverlay message={t("session.creating")} />;
  if (error) {
    return (
      <div className="empty-state session-gate-empty">
        <p>{t("session.failed")}</p>
        <p className="text-secondary session-gate-hint">
          {t("session.failedDetail", { datasetId })}
        </p>
      </div>
    );
  }
  if (!sessionId) return null;

  return <>{children({ sessionId, datasetId })}</>;
}
