import { useState, useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/Toast";
import { PageShell } from "../components/PageShell";
import { useStudioSettings } from "../context/StudioSettingsContext";
import { studioApi } from "../services/api";

interface TrainingJob {
  id: string;
  model_name: string;
  dataset_id: string;
  status: "pending" | "running" | "completed" | "failed";
  progress_pct: number;
  accuracy: number | null;
  model_type: string;
  epochs: number;
  created_at: string;
  error_message?: string;
  artifact_path?: string;
}

interface DeployedModel {
  id: string;
  training_job_id: string;
  model_name: string;
  model_type: string;
  version: string;
  dataset_id: string;
  accuracy: number | null;
  is_active: boolean;
  deployed_at: string | null;
  created_at: string;
}

const MODEL_TYPE_KEYS = [
  "road_segmentation",
  "agri_crop_classification",
  "agri_health_classification",
  "object_detection",
  "classification",
] as const;

export default function TrainingPage({ datasetId }: { datasetId: string }) {
  const { t } = useTranslation();
  const [modelName, setModelName] = useState("yolov8n-seg");
  const [modelType, setModelType] = useState("road_segmentation");
  const [epochs, setEpochs] = useState(50);
  const [batchSize, setBatchSize] = useState(16);
  const [learningRate, setLearningRate] = useState("0.001");
  const [starting, setStarting] = useState(false);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [jobsError, setJobsError] = useState(false);
  const [models, setModels] = useState<DeployedModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState(false);
  const [deployingJobId, setDeployingJobId] = useState<string | null>(null);
  const [activatingModelId, setActivatingModelId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { showToast } = useToast();
  const { expertMode } = useStudioSettings();

  const fetchJobs = useCallback(async () => {
    try {
      const res = await studioApi.listTrainingJobs({ page_size: 50 });
      setJobs(res.data.items ?? []);
      setJobsError(false);
    } catch {
      setJobsError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchModels = useCallback(async () => {
    try {
      const res = await studioApi.listDeployedModels({ page_size: 50 });
      setModels(res.data.items ?? []);
      setModelsError(false);
    } catch {
      setModelsError(true);
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
    fetchModels();
    pollRef.current = setInterval(fetchJobs, 5000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchJobs, fetchModels]);

  const handleStartTraining = useCallback(async () => {
    if (!datasetId) {
      showToast(t("training.selectDatasetFirst"), "error");
      return;
    }
    setStarting(true);
    try {
      await studioApi.startTraining(datasetId, {
        model_name: modelName,
        model_type: modelType,
        epochs,
        batch_size: batchSize,
        learning_rate: parseFloat(learningRate),
      });
      showToast(t("training.submitSuccess"), "success");
      fetchJobs();
    } catch {
      showToast(t("training.submitFailed"), "error");
    } finally {
      setStarting(false);
    }
  }, [datasetId, modelName, modelType, epochs, batchSize, learningRate, showToast, fetchJobs, t]);

  const handleDeploy = useCallback(async (jobId: string) => {
    setDeployingJobId(jobId);
    try {
      await studioApi.deployModel(jobId);
      showToast(t("training.deploySuccess"), "success");
      fetchModels();
    } catch {
      showToast(t("training.deployFailed"), "error");
    } finally {
      setDeployingJobId(null);
    }
  }, [showToast, fetchModels, t]);

  const handleActivate = useCallback(async (modelId: string) => {
    setActivatingModelId(modelId);
    try {
      await studioApi.activateModel(modelId);
      showToast(t("training.activateSuccess"), "success");
      fetchModels();
    } catch {
      showToast(t("training.activateFailed"), "error");
    } finally {
      setActivatingModelId(null);
    }
  }, [showToast, fetchModels, t]);

  const statusLabel = (status: string) => {
    const map: Record<string, string> = {
      pending: t("training.statusPending"),
      running: t("training.statusRunning"),
      completed: t("training.statusCompleted"),
      failed: t("training.statusFailed"),
    };
    return map[status] ?? status;
  };

  const hasRunningForDataset = jobs.some(
    (j) => j.dataset_id === datasetId && (j.status === "pending" || j.status === "running"),
  );
  const hasRunningElsewhere = jobs.some(
    (j) => j.dataset_id !== datasetId && (j.status === "pending" || j.status === "running"),
  );
  const deployedJobIds = new Set(models.map((m) => m.training_job_id));

  return (
    <PageShell
      accent="training"
      className="training-layout"
      title={t("training.title")}
      subtitle={t("training.subtitle")}
      badge={datasetId || undefined}
    >
      <div className="training-config-panel ui-panel ui-panel--accent-top">
        <div className="ui-panel-header">
          <h3>{t("training.configTitle")}</h3>
        </div>
        <div className="training-config">
          <div>
            <div className="form-group">
              <label>{t("training.modelName")}</label>
              <input
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                placeholder={t("training.modelNamePlaceholder")}
              />
              <span className="help-text">{t("training.modelNameHelp")}</span>
            </div>
            <div className="form-group">
              <label>{t("training.modelType")}</label>
              <select value={modelType} onChange={(e) => setModelType(e.target.value)}>
                {MODEL_TYPE_KEYS.map((key) => (
                  <option key={key} value={key}>{t(`training.modelTypes.${key}`)}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>{t("training.dataset")}</label>
              <input value={datasetId || t("training.noneSelected")} disabled />
              <span className="help-text">{t("training.datasetHelp")}</span>
            </div>
          </div>
          <div>
            <div className="form-group">
              <label>{t("training.epochs")}</label>
              <input type="number" value={epochs} onChange={(e) => setEpochs(parseInt(e.target.value) || 50)} min={1} max={1000} />
              <span className="help-text">{t("training.epochsHelp")}</span>
            </div>
            {expertMode && (
              <>
                <div className="form-group">
                  <label>{t("training.batchSize")}</label>
                  <input type="number" value={batchSize} onChange={(e) => setBatchSize(parseInt(e.target.value) || 16)} min={1} max={256} />
                  <span className="help-text">{t("training.batchSizeHelp")}</span>
                </div>
                <div className="form-group">
                  <label>{t("training.learningRate")}</label>
                  <input value={learningRate} onChange={(e) => setLearningRate(e.target.value)} placeholder="0.001" />
                  <span className="help-text">{t("training.learningRateHelp")}</span>
                </div>
              </>
            )}
          </div>
        </div>
        <button
          className="btn btn-primary"
          onClick={handleStartTraining}
          disabled={starting || !datasetId || hasRunningForDataset}
        >
          {starting
            ? t("training.starting")
            : hasRunningForDataset
              ? t("training.runningThisDataset")
              : t("training.startTraining")}
        </button>
        {hasRunningElsewhere && !hasRunningForDataset && (
          <p className="help-text">{t("training.runningOtherDataset")}</p>
        )}
      </div>

      <div className="training-jobs-panel ui-panel">
        <h3>
          {t("training.historyTitle")}
          {hasRunningForDataset && (
            <span className="badge badge-warning training-badge-inline">
              {t("training.liveBadge")}
            </span>
          )}
        </h3>
        {loading ? (
          <div className="empty-state"><p>{t("training.loading")}</p></div>
        ) : jobsError ? (
          <div className="empty-state error-notice"><p>{t("training.loadFailed")}</p></div>
        ) : jobs.length === 0 ? (
          <div className="empty-state"><p>{t("training.noJobs")}</p></div>
        ) : (
          jobs.map((job) => (
            <div key={job.id} className="training-job-row">
              <span className="job-model">{job.model_name}</span>
              <span className="job-dataset">{job.dataset_id}</span>
              <span className="job-progress">
                <div className="progress-bar">
                  <div
                    className={`progress-fill ${job.status === "completed" ? "complete" : job.status === "failed" ? "failed" : ""}`}
                    style={{ "--progress": `${job.progress_pct}%` } as React.CSSProperties}
                  />
                </div>
              </span>
              <span className={`status-badge ${job.status}`}>
                {statusLabel(job.status)} {job.progress_pct}%
              </span>
              <span className="job-accuracy">
                {job.accuracy !== null
                  ? t("training.mapScore", { value: (job.accuracy * 100).toFixed(1) })
                  : job.status === "failed"
                    ? job.error_message?.slice(0, 40) ?? t("training.errorShort")
                    : "--"}
              </span>
              {job.status === "completed" && (
                <button
                  className="btn btn-sm btn-inline-spaced"
                  onClick={() => handleDeploy(job.id)}
                  disabled={deployingJobId === job.id || deployedJobIds.has(job.id)}
                >
                  {deployedJobIds.has(job.id)
                    ? t("training.deployed")
                    : deployingJobId === job.id
                      ? t("training.deploying")
                      : t("training.deploy")}
                </button>
              )}
            </div>
          ))
        )}
      </div>

      <div className="training-history model-registry-section">
        <h3>{t("training.modelsTitle")}</h3>
        {modelsLoading ? (
          <div className="empty-state"><p>{t("training.loading")}</p></div>
        ) : modelsError ? (
          <div className="empty-state error-notice"><p>{t("training.modelsLoadFailed")}</p></div>
        ) : models.length === 0 ? (
          <div className="empty-state"><p>{t("training.noModels")}</p></div>
        ) : (
          models.map((m) => (
            <div key={m.id} className="training-job-row model-registry-row">
              <span className="job-model">{m.model_name}</span>
              <span className="job-dataset">{t(`training.modelTypes.${m.model_type as typeof MODEL_TYPE_KEYS[number]}`, m.model_type)}</span>
              <span className="job-dataset">{m.version}</span>
              <span className={`status-badge ${m.is_active ? "completed" : "pending"}`}>
                {m.is_active ? t("training.active") : t("training.inactive")}
              </span>
              <span className="job-accuracy">
                {m.accuracy !== null ? t("training.mapScore", { value: (m.accuracy * 100).toFixed(1) }) : "--"}
              </span>
              {!m.is_active && (
                <button
                  className="btn btn-success btn-sm btn-inline-spaced"
                  onClick={() => handleActivate(m.id)}
                  disabled={activatingModelId === m.id}
                >
                  {activatingModelId === m.id ? t("training.activating") : t("training.activate")}
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </PageShell>
  );
}
