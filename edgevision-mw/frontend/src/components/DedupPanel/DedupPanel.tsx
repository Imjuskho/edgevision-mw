import React, { useState, useCallback, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import api from "../../services/api";
import { useToast } from "../Toast";
import { PageShell } from "../PageShell";
import { useStudioSettings } from "../../context/StudioSettingsContext";

interface DuplicateImage {
  image_id: string;
  image_path: string;
  node_id: string;
  capture_time: string;
  thumbnail_url: string;
  annotation_id: string;
}

interface DuplicateGroup {
  group_id: string;
  similarity: number;
  method: string;
  images: DuplicateImage[];
}

interface Props {
  datasetId: string;
  onNavigate?: (path: string) => void;
}

const EMBED_CONCURRENCY = 3;

export const DedupPanel: React.FC<Props> = ({ datasetId, onNavigate }) => {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const { expertMode, settings } = useStudioSettings();
  const embedCancelRef = useRef(false);
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [resolutions, setResolutions] = useState<Record<string, string>>({});
  const [activeGroupIndex, setActiveGroupIndex] = useState(0);
  const [threshold, setThreshold] = useState(settings.operational.dedupDefaultThreshold);
  const [methods, setMethods] = useState<string[]>(settings.operational.dedupDefaultMethods);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzeProgress, setAnalyzeProgress] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [embedStatus, setEmbedStatus] = useState<string | null>(null);
  const [isEmbedding, setIsEmbedding] = useState(false);
  const [embedProgress, setEmbedProgress] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setThreshold(settings.operational.dedupDefaultThreshold);
    setMethods(settings.operational.dedupDefaultMethods);
  }, [settings.operational.dedupDefaultThreshold, settings.operational.dedupDefaultMethods]);

  const startAnalysis = async () => {
    setIsAnalyzing(true);
    setAnalyzeProgress(5);
    setError(null);
    try {
      const res = await api.post("/studio/dedup/analyze", {
        dataset_id: datasetId,
        methods,
        threshold,
      });
      setJobId(res.data.job_id);
      pollJob(res.data.job_id);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : t("dedup.startFailed"));
      setIsAnalyzing(false);
    }
  };

  const pollJob = useCallback((id: string) => {
    let attempts = 0;
    const maxAttempts = 60;
    const interval = setInterval(async () => {
      attempts++;
      setAnalyzeProgress(Math.min(95, 5 + (attempts / maxAttempts) * 90));
      try {
        const res = await api.get(`/studio/dedup/results/${id}`);
        if (res.data.status === "COMPLETED") {
          clearInterval(interval);
          setAnalyzeProgress(100);
          setGroups(res.data.result?.groups || []);
          setIsAnalyzing(false);
        } else if (res.data.status === "FAILED") {
          clearInterval(interval);
          setIsAnalyzing(false);
          setAnalyzeProgress(0);
          setError(t("dedup.analysisFailed"));
        } else if (attempts >= maxAttempts) {
          clearInterval(interval);
          setIsAnalyzing(false);
          setAnalyzeProgress(0);
          setError(t("dedup.analysisTimeout"));
        }
      } catch {
        clearInterval(interval);
        setIsAnalyzing(false);
        setAnalyzeProgress(0);
        setError(t("dedup.pollFailed"));
      }
    }, 2000);
  }, [t]);

  const resolveGroup = (groupId: string, action: string) => {
    setResolutions((prev) => ({ ...prev, [groupId]: action }));
    const nextIndex = groups.findIndex((g, i) => i > activeGroupIndex && !resolutions[g.group_id]);
    if (nextIndex !== -1) setActiveGroupIndex(nextIndex);
  };

  const submitResolutions = async () => {
    const actions = Object.entries(resolutions).map(([groupId, action]) => ({
      group_id: groupId,
      action,
    }));
    setSubmitting(true);
    try {
      await api.post("/studio/dedup/resolve", {
        dataset_id: datasetId,
        resolutions: actions,
      });
      showToast(t("dedup.resolveSuccess"), "success");
      onNavigate?.("/health");
    } catch {
      showToast(t("dedup.resolveFailed"), "error");
    } finally {
      setSubmitting(false);
    }
  };

  const cancelEmbeddings = () => {
    embedCancelRef.current = true;
    setEmbedStatus(t("dedup.embedCancelled"));
  };

  const computeEmbeddings = async () => {
    embedCancelRef.current = false;
    setIsEmbedding(true);
    setEmbedProgress(0);
    setEmbedStatus(t("dedup.embedStatus"));
    try {
      const res = await api.get(`/studio/datasets/${datasetId}/images?page=1&page_size=200`);
      const images: DuplicateImage[] = res.data.images || [];
      let computed = 0;
      let failed = 0;
      let index = 0;

      const worker = async () => {
        while (index < images.length) {
          if (embedCancelRef.current) return;
          const i = index++;
          const img = images[i];
          try {
            await api.post("/studio/clip/embed", {}, {
              params: { annotation_id: img.annotation_id },
            });
            computed++;
          } catch {
            failed++;
          }
          setEmbedProgress(((computed + failed) / images.length) * 100);
          await new Promise((r) => setTimeout(r, 0));
        }
      };

      await Promise.all(
        Array.from({ length: Math.min(EMBED_CONCURRENCY, images.length || 1) }, () => worker()),
      );

      if (embedCancelRef.current) {
        setEmbedStatus(t("dedup.embedCancelled"));
      } else if (failed > 0) {
        setEmbedStatus(t("dedup.embedPartial", { done: computed, total: images.length, failed }));
      } else {
        setEmbedStatus(t("dedup.embedComplete", { done: computed, total: images.length }));
      }
    } catch {
      setEmbedStatus(t("dedup.embedFailed"));
      setEmbedProgress(0);
    } finally {
      setIsEmbedding(false);
    }
  };

  const activeGroup = groups[activeGroupIndex];
  const progressPercent =
    groups.length > 0 ? (Object.keys(resolutions).length / groups.length) * 100 : 0;

  const methodLabel = (m: string) => {
    if (m === "phash") return t("dedup.methodPhash");
    if (m === "clip") return t("dedup.methodClip");
    return t("dedup.methodGps");
  };

  return (
    <PageShell
      accent="quality"
      title={t("dedup.title")}
      subtitle={t("dedup.subtitle", "Find and resolve duplicate images before they affect training quality.")}
      badge={datasetId}
    >
    <div className="dedup-panel dedup-page-panel">
      {groups.length > 0 && (
        <div className="dedup-stats dedup-stats-spaced">
          <span>{groups.length} {t("dedup.groups")}</span>
          <span>{Object.keys(resolutions).length} {t("dedup.resolved")}</span>
        </div>
      )}

      {error && (
        <div className="error-notice error-notice--dedup">{error}</div>
      )}

      {!jobId && (
        <div className="dedup-config">
          <h3>{t("dedup.configTitle")}</h3>
          {!expertMode && (
            <p className="dedup-expert-hint">
              {t("dedup.basicHint", "Using default thresholds. Enable Expert mode in Settings for advanced tuning.")}
            </p>
          )}
          {expertMode && (
          <div className="dedup-options">
            <label>
              {t("dedup.similarityThreshold")}:
              <input
                type="range"
                min="0.80"
                max="0.99"
                step="0.01"
                value={threshold}
                aria-valuemin={0.8}
                aria-valuemax={0.99}
                aria-valuenow={threshold}
                aria-label={t("dedup.similarityThreshold")}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
              />
              <span>{(threshold * 100).toFixed(0)}%</span>
            </label>

            <div className="dedup-methods">
              {(["phash", "clip", "gps_temporal"] as const).map((m) => (
                <label key={m}>
                  <input
                    type="checkbox"
                    checked={methods.includes(m)}
                    onChange={(e) => {
                      if (e.target.checked) setMethods([...methods, m]);
                      else setMethods(methods.filter((x) => x !== m));
                    }}
                  />
                  {methodLabel(m)}
                </label>
              ))}
            </div>
          </div>
          )}
          <button className="dedup-start-btn" onClick={startAnalysis} disabled={isAnalyzing}>
            {isAnalyzing ? t("dedup.analyzing") : t("dedup.startAnalysis")}
          </button>

          {expertMode && (
          <div className="dedup-embed-section">
            <div className="dedup-embed-actions">
              <button
                onClick={computeEmbeddings}
                disabled={isEmbedding}
                className="btn btn-sm btn--purple-outline"
              >
                {isEmbedding ? t("dedup.computing") : t("dedup.computeEmbeddings")}
              </button>
              {isEmbedding && (
                <button type="button" className="btn btn-sm" onClick={cancelEmbeddings}>
                  {t("dedup.cancelEmbed")}
                </button>
              )}
            </div>
            {isEmbedding && (
              <div className="dedup-progress dedup-embed-progress">
                <div className="progress-bar">
                  <div className="progress-fill" style={{ "--progress": `${embedProgress}%` } as React.CSSProperties} />
                </div>
              </div>
            )}
            {embedStatus && (
              <span className="dedup-embed-status">
                {embedStatus}
              </span>
            )}
          </div>
          )}
        </div>
      )}

      {isAnalyzing && (
        <div className="dedup-progress">
          <div className="progress-bar">
            <div className="progress-fill" style={{ "--progress": `${analyzeProgress}%` } as React.CSSProperties} />
          </div>
          <p>{t("dedup.clustering")}</p>
        </div>
      )}

      {!isAnalyzing && groups.length > 0 && activeGroup && (
        <>
          <div className="dedup-resolution-progress">
            <div className="progress-bar">
              <div className="progress-fill" style={{ "--progress": `${progressPercent}%` } as React.CSSProperties} />
            </div>
            <span>
              {t("dedup.groupsReviewed", {
                done: Object.keys(resolutions).length,
                total: groups.length,
              })}
            </span>
          </div>

          <div className="dedup-navigator">
            <button
              onClick={() => setActiveGroupIndex(Math.max(0, activeGroupIndex - 1))}
              disabled={activeGroupIndex === 0}
              aria-label={t("dedup.prev")}
            >
              {t("dedup.prev")}
            </button>
            <span>{t("dedup.groupOf", { current: activeGroupIndex + 1, total: groups.length })}</span>
            <button
              onClick={() => setActiveGroupIndex(Math.min(groups.length - 1, activeGroupIndex + 1))}
              disabled={activeGroupIndex === groups.length - 1}
              aria-label={t("dedup.next")}
            >
              {t("dedup.next")}
            </button>
          </div>

          <div className="dedup-group-detail">
            <div className="group-meta">
              <span className="group-method">{activeGroup.method}</span>
              <span className="group-similarity">
                {(activeGroup.similarity * 100).toFixed(1)}% {t("dedup.similar")}
              </span>
              {resolutions[activeGroup.group_id] && (
                <span className="group-resolved">{resolutions[activeGroup.group_id]}</span>
              )}
            </div>

            <div className="group-images">
              {activeGroup.images.map((img, idx) => (
                <div key={img.image_id} className="dedup-image-card">
                  <img src={img.thumbnail_url} alt={`${img.node_id} ${idx + 1}`} loading="lazy" />
                  <div className="img-meta">
                    <span className="img-node">{img.node_id}</span>
                    <span className="img-time">
                      {img.capture_time ? new Date(img.capture_time).toLocaleString() : t("dedup.unknownTime")}
                    </span>
                  </div>
                  <div className="img-number">#{idx + 1}</div>
                </div>
              ))}
            </div>

            <div className="group-actions">
              <button
                className="action-keep-first"
                onClick={() => resolveGroup(activeGroup.group_id, "keep_first")}
                disabled={!!resolutions[activeGroup.group_id]}
              >
                {t("dedup.keepFirstOnly")}
              </button>
              <button
                className="action-keep-best"
                onClick={() => resolveGroup(activeGroup.group_id, "keep_best")}
                disabled={!!resolutions[activeGroup.group_id]}
              >
                {t("dedup.keepBest")}
              </button>
              <button
                className="action-keep-all"
                onClick={() => resolveGroup(activeGroup.group_id, "keep_all")}
                disabled={!!resolutions[activeGroup.group_id]}
              >
                {t("dedup.keepAll")}
              </button>
              <button
                className="action-remove-all"
                onClick={() => resolveGroup(activeGroup.group_id, "remove_all")}
                disabled={!!resolutions[activeGroup.group_id]}
              >
                {t("dedup.removeAll")}
              </button>
            </div>
          </div>

          <div className="dedup-bulk">
            {expertMode && (
            <button
              onClick={() => {
                groups.forEach((g) => {
                  if (!resolutions[g.group_id]) resolveGroup(g.group_id, "keep_first");
                });
              }}
            >
              {t("dedup.autoResolveAll")}
            </button>
            )}
            <button
              className="dedup-submit"
              onClick={submitResolutions}
              disabled={Object.keys(resolutions).length === 0 || submitting}
            >
              {t("dedup.applyCount", { count: Object.keys(resolutions).length })}
            </button>
          </div>
        </>
      )}

      {!isAnalyzing && jobId && groups.length === 0 && (
        <div className="dedup-empty">
          <h3>{t("dedup.noDuplicates")}</h3>
          <p>{t("dedup.emptyHint")}</p>
        </div>
      )}
    </div>
    </PageShell>
  );
};
