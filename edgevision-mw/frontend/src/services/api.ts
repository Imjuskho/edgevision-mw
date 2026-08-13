import axios from "axios";

const API_BASE = "/api/v1";

/** Rural/solar links: fail fast so resilient save can queue instead of hanging indefinitely. */
const REQUEST_TIMEOUT_MS = 45_000;

const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
  timeout: REQUEST_TIMEOUT_MS,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("studio_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("studio_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;

export const studioApi = {
  createSession: (datasetId: string) =>
    api.post("/studio/sessions", { dataset_id: datasetId }),

  getSession: (sessionId: string) =>
    api.get(`/studio/sessions/${sessionId}`),

  listImages: (datasetId: string, page = 1, pageSize = 50) =>
    api.get(`/studio/datasets/${datasetId}/images`, {
      params: { page, page_size: pageSize },
    }),

  saveAnnotation: (
    sessionId: string,
    imageIndex: number,
    annotations: { x: number; y: number; width: number; height: number; label: string; confidence?: number; category?: string; attributes?: string[] }[],
    toolUsed = "bbox"
  ) =>
    api.post("/studio/annotations/save", {
      session_id: sessionId,
      image_index: imageIndex,
      annotations,
      tool_used: toolUsed,
    }),

  serveImage: (annotationId: string) =>
    `/api/v1/studio/images/${annotationId}/serve`,

  getHealth: (datasetId: string) =>
    api.get(`/studio/datasets/${datasetId}/health`),

  createExport: (datasetId: string, format = "coco") =>
    api.post("/studio/exports", { dataset_id: datasetId, format }),

  getExport: (exportId: string) =>
    api.get(`/studio/exports/${exportId}`),

  login: (email: string, password: string) =>
    api.post("/auth/login", { email, password }),

  register: (email: string, password: string, fullName: string) =>
    api.post("/auth/register", { email, password, full_name: fullName }),

  // Phase 7 — Image Ingestion
  uploadImages: (datasetId: string, files: File[], source = "file") => {
    const normalizedSource = source === "screen" ? "screen_capture" : source;
    const formData = new FormData();
    formData.append("dataset_id", datasetId);
    formData.append("source", normalizedSource);
    files.forEach((file) => formData.append("files", file));
    return api.post("/upload/images", formData);
  },

  uploadImageFromUrl: (datasetId: string, url: string, source = "url") => {
    const formData = new FormData();
    formData.append("dataset_id", datasetId);
    formData.append("url", url);
    formData.append("source", source);
    return api.post("/upload/url", formData);
  },

  checkDuplicates: (checksums: string[]) =>
    api.post("/upload/duplicates", { checksums }),

  // Phase 7 — Annotator Assignment
  createAssignment: (datasetId: string, annotatorIds: string[], deadline?: string, priority = "NORMAL") =>
    api.post("/assignments", { dataset_id: datasetId, annotator_ids: annotatorIds, deadline, priority }),

  listAssignments: (params?: { dataset_id?: string; status?: string }) =>
    api.get("/assignments", { params }),

  getQueue: () =>
    api.get("/assignments/queue"),

  claimAssignment: (assignmentId: string) =>
    api.post(`/assignments/${assignmentId}/claim`),

  submitAssignment: (assignmentId: string) =>
    api.post(`/assignments/${assignmentId}/submit`),

  // Phase 7 — QA Review
  getReviewQueue: (params?: { status?: string; page?: number; page_size?: number }) =>
    api.get("/review/queue", { params }),

  getReviewJobDetail: (assignmentId: string) =>
    api.get(`/review/jobs/${assignmentId}`),

  certifyJob: (assignmentId: string) =>
    api.post(`/review/jobs/${assignmentId}/certify`),

  rejectJob: (assignmentId: string, reason: string) =>
    api.post(`/review/jobs/${assignmentId}/reject`, { rejection_reason: reason }),

  getIAAMetrics: (assignmentId: string) =>
    api.get(`/review/jobs/${assignmentId}/iaa`),

  approveAnnotation: (assignmentId: string, annotationId: string) =>
    api.post(`/review/jobs/${assignmentId}/annotations/${annotationId}/approve`),

  rejectAnnotation: (assignmentId: string, annotationId: string, reason: string) =>
    api.post(`/review/jobs/${assignmentId}/annotations/${annotationId}/reject`, { reason }),

  // Phase 8.3 — CLIP Embedding
  embedImage: (file: File, annotationId?: string) => {
    const formData = new FormData();
    formData.append("file", file);
    if (annotationId) formData.append("annotation_id", annotationId);
    return api.post("/studio/clip/embed", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  computeSimilarity: (imageAId: string, imageBId: string) =>
    api.post("/studio/clip/similarity", { image_a_id: imageAId, image_b_id: imageBId }),

  // Phase 8.2 — Pre-labeling
  prelabelImage: (file: File, confidenceThreshold = 0.45) => {
    const formData = new FormData();
    formData.append("file", file);
    return api.post(`/studio/prelabel/image?confidence_threshold=${confidenceThreshold}`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  // Phase 8 — Road Segmentation
  segmentRoad: (imageId: string, confThreshold = 0.5, iouThreshold = 0.45, returnPolygons = true) =>
    api.post("/road/segment", {
      image_id: imageId,
      conf_threshold: confThreshold,
      iou_threshold: iouThreshold,
      return_polygons: returnPolygons,
    }),

  segmentRoadBatch: (
    imageIds: string[],
    confThreshold = 0.5,
    iouThreshold = 0.45,
  ) =>
    api.post("/road/segment/batch", {
      image_ids: imageIds,
      conf_threshold: confThreshold,
      iou_threshold: iouThreshold,
    }),

  segmentRoadDatasetBatch: (
    datasetId: string,
    options: { scope?: "remaining" | "all"; force?: boolean; confThreshold?: number; iouThreshold?: number } = {},
  ) =>
    api.post("/road/segment/batch", {
      dataset_id: datasetId,
      scope: options.scope ?? "remaining",
      force: options.force ?? false,
      conf_threshold: options.confThreshold ?? 0.5,
      iou_threshold: options.iouThreshold ?? 0.45,
    }),

  prelabelDatasetBatch: (
    datasetId: string,
    options: { scope?: "remaining" | "all"; force?: boolean; confidenceThreshold?: number } = {},
  ) =>
    api.post("/studio/prelabel/batch", {
      dataset_id: datasetId,
      scope: options.scope ?? "remaining",
      force: options.force ?? false,
      confidence_threshold: options.confidenceThreshold ?? 0.45,
    }),

  getBatchJobStatus: (jobId: string) =>
    api.get(`/studio/prelabel/jobs/${jobId}`),

  getRoadResult: (annotationId: string) =>
    api.get(`/road/result/${annotationId}`),

  updateRoadResult: (annotationId: string, update: { instances?: unknown[]; surface_type?: string; reviewed?: boolean }) =>
    api.patch(`/road/result/${annotationId}`, update),

  getRoadClasses: () =>
    api.get("/road/classes"),

  analyzeRoadCondition: (datasetId: string, confThreshold = 0.5) =>
    api.post("/road/analyze", {
      dataset_id: datasetId,
      conf_threshold: confThreshold,
    }),

  // Phase 8 — Training
  listDatasets: (params?: { page?: number; page_size?: number; status?: string; search?: string }) =>
    api.get("/datasets/", { params }),

  createDataset: (body: { name: string; dataset_id?: string; source_type?: string; description?: string }) =>
    api.post("/studio/datasets", body),

  startTraining: (datasetId: string, config: { model_name: string; model_type: string; epochs: number; batch_size: number; learning_rate: number }) =>
    api.post("/studio/training/start", {
      dataset_id: datasetId,
      ...config,
    }),

  listTrainingJobs: (params?: { page?: number; page_size?: number; dataset_id?: string }) =>
    api.get("/studio/training/", { params }),

  getTrainingJob: (jobId: string) =>
    api.get(`/studio/training/${jobId}`),

  cancelTrainingJob: (jobId: string) =>
    api.post(`/studio/training/${jobId}/cancel`),

  // Model Registry
  listDeployedModels: (params?: { model_type?: string; is_active?: boolean; page?: number; page_size?: number }) =>
    api.get("/studio/models/", { params }),

  deployModel: (trainingJobId: string, notes?: string) =>
    api.post("/studio/models/deploy", { training_job_id: trainingJobId, notes }),

  activateModel: (modelId: string) =>
    api.post(`/studio/models/${modelId}/activate`),

  getModelDetail: (modelId: string) =>
    api.get(`/studio/models/${modelId}`),

  getCurrentUser: () => api.get("/auth/me"),

  getUserSettings: () => api.get("/auth/me/settings"),

  patchUserSettings: (patch: Record<string, unknown>) =>
    api.patch("/auth/me/settings", patch),

  listAuditLogs: (params?: { event_type?: string; limit?: number; offset?: number }) =>
    api.get("/auth/audit-logs", { params }),

  listUsers: (params?: { role?: string }) => api.get("/auth/users", { params }),

  syncBatch: (
    sessionId: string,
    actions: Array<{ image_id: string; action_type: string; payload: any }>,
    ifMatch: string | undefined = "*"
  ) =>
    api.post(
      "/studio/sync/batch",
      { session_id: sessionId, actions },
      { headers: { "If-Match": ifMatch || "*" } }
    ),

  saveRoadAnnotations: (sessionId: string, imageIndex: number, annotations: unknown[], toolUsed = "polygon") =>
    api.post("/studio/annotations/save", {
      session_id: sessionId,
      image_index: imageIndex,
      annotations,
      tool_used: toolUsed,
    }),

  getAnnotationData: (annotationId: string) =>
    api.get(`/studio/annotations/${annotationId}`),

  // Agricultural Analysis
  analyzeAgriCondition: (datasetId: string, confThreshold = 0.35) =>
    api.post("/agri/analyze", {
      dataset_id: datasetId,
      conf_threshold: confThreshold,
    }),

  segmentAgri: (imageId: string, confThreshold = 0.35, iouThreshold = 0.45, returnPolygons = true) =>
    api.post("/agri/segment", {
      image_id: imageId,
      conf_threshold: confThreshold,
      iou_threshold: iouThreshold,
      return_polygons: returnPolygons,
    }),

  getAgriClasses: () =>
    api.get("/agri/classes"),

  // Fleet / Node Management
  listNodes: (params?: { district?: string; category?: string; status?: string }) =>
    api.get("/nodes/", { params }),

  getNodeDetail: (nodeId: string) =>
    api.get(`/nodes/${nodeId}`),

  getNodeTelemetry: (nodeId: string, hours = 24) =>
    api.get(`/nodes/${nodeId}/telemetry`, { params: { hours } }),

  getNodeAlerts: () =>
    api.get("/nodes/alerts"),

  sendNodeCommand: (nodeId: string, command: string, payload: Record<string, unknown> = {}) =>
    api.post(`/nodes/${nodeId}/command`, { command, payload }),

  // Live Annotation
  saveLiveAnnotation: (formData: FormData) =>
    api.post("/annotations/live", formData),
};
