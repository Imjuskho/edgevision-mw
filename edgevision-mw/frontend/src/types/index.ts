export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
}

export interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
}

export interface AnnotationSession {
  id: string;
  user_id: string;
  dataset_id: string;
  started_at: string;
  ended_at: string | null;
  image_count: number;
  annotations_created: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  category?: string;
  confidence?: number;
  attributes?: string[];
  /** Normalized polygon from YOLOv8-seg prelabel (0..1 coords) */
  polygon?: [number, number][];
  /** Inference engine: server_yolov8n_seg | browser_yolov8n_seg | yolov8n_cls | grid */
  engine?: string;
  annotationId?: string;
  /** Monocular 3D payload from live capture (read-only hint in studio) */
  bbox_3d?: Record<string, unknown>;
  track_id?: number;
}

export interface ImageItem {
  index: number;
  annotation_id: string;
  image_path: string;
  thumbnail_path: string;
  status: string;
  has_human_labels: boolean;
}

export interface ImageListResponse {
  dataset_id: string;
  total: number;
  page: number;
  page_size: number;
  images: ImageItem[];
}

export interface HealthScore {
  dataset_id: string;
  overall_score: number;
  completeness_pct: number;
  consistency_pct: number;
  accuracy_pct: number;
  timeliness_pct: number;
  recommendations: string[];
}

export interface ExportJob {
  id: string;
  dataset_id: string;
  user_id: string;
  status: string;
  format: string;
  progress_pct: number;
  file_size_bytes: number | null;
  download_url: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

// ─── AI Assist Types ────────────────────────────────────────────────────────

export type AIPromptType = 'point' | 'box' | 'full_image';

export interface AIAssistRequest {
  image_id?: string;
  image_data?: string;
  prompt_type: AIPromptType;
  prompt_data: Record<string, unknown>;
  model_preference?: 'fast' | 'accurate';
  return_polygons?: boolean;
}

export interface AIAnnotation {
  class_name: string;
  confidence: number;
  bbox: [number, number, number, number];
  polygon?: [number, number][];
}

export interface AIAssistResponse {
  annotations: AIAnnotation[];
  inference_time_ms: number;
  model_used: string;
  fallback: boolean;
}

// ─── Dedup Types ────────────────────────────────────────────────────────────

export type DedupMethod = 'phash' | 'clip' | 'gps_temporal';

export interface DuplicateImage {
  image_id: string;
  image_path: string;
  node_id: string;
  capture_time: string;
  thumbnail_url: string;
}

export interface DuplicateGroup {
  group_id: string;
  similarity: number;
  method: DedupMethod;
  images: DuplicateImage[];
}

export interface DedupAnalyzeRequest {
  dataset_id: string;
  methods: DedupMethod[];
  threshold: number;
}

export interface DedupAnalyzeResponse {
  job_id: string;
  estimated_seconds: number;
}

export type DedupResolution = 'keep_first' | 'keep_best' | 'keep_all' | 'remove_all';

export interface DedupResolveRequest {
  dataset_id: string;
  resolutions: {
    group_id: string;
    action: DedupResolution;
  }[];
}

export interface DedupResultsResponse {
  status: 'pending' | 'running' | 'complete' | 'failed';
  total_groups: number;
  total_duplicates: number;
  result?: {
    groups: DuplicateGroup[];
  };
}

// ─── Sync Types ─────────────────────────────────────────────────────────────

export type SyncActionType = 'create' | 'edit' | 'delete' | 'approve' | 'reject';

export interface SyncAction {
  annotation_id: string;
  action_type: SyncActionType;
  payload?: Record<string, unknown>;
  client_timestamp?: string;
  etag?: string;
}

export interface SyncBatchRequest {
  session_id: string;
  actions: SyncAction[];
  client_version?: string;
}

export interface SyncConflict {
  annotation_id: string;
  server_version: Record<string, unknown> | null;
  client_version: Record<string, unknown> | null;
  resolution: string;
}

export interface SyncBatchResponse {
  committed: string[];
  conflicts: SyncConflict[];
  rejected: { annotation_id: string; reason: string }[];
  server_timestamp: string;
}

export interface SyncStatusChange {
  annotation_id: string;
  image_index: number;
  status: string;
  updated_at: string | null;
  etag: string | null;
}

export interface SyncStatusResponse {
  session_id: string;
  server_changes: SyncStatusChange[];
  session_active: boolean;
  has_more: boolean;
}

// ─── Dataset Types ──────────────────────────────────────────────────────────

export interface Dataset {
  id: string;
  dataset_id: string;
  name: string;
  status: string;
  sample_count: number;
  classes: Record<string, number>;
  price_usd: number;
  license_type: string;
  consent_coverage_pct: number;
  iaa_score: number;
  created_at: string;
  updated_at: string;
  dataset_type?: string;
  labeler?: string;
}

export interface ClassDistribution {
  class_name: string;
  count: number;
  percentage: number;
}

export interface CaptureRecommendation {
  node_id: string;
  recommendation: string;
  priority: 'high' | 'medium' | 'low';
}

// ─── Health History Types ───────────────────────────────────────────────────

export interface HealthSnapshot {
  time: string;
  overall_score: number;
  uniqueness_score: number;
  balance_score: number;
  coverage_score: number;
  confidence_score: number;
}

export interface HealthHistoryResponse {
  dataset_id: string;
  snapshots: HealthSnapshot[];
}

// ─── Road Segmentation Types (Phase 8) ─────────────────────────────────────

export interface InstanceMask {
  class_id: number;
  class_name: string;
  confidence: number;
  bbox: [number, number, number, number];
  mask_rle: string;
  polygon?: [number, number][];
}

export interface RoadSegmentationRequest {
  image_id: string;
  conf_threshold?: number;
  iou_threshold?: number;
  return_polygons?: boolean;
}

export interface RoadSegmentationResponse {
  image_id: string;
  instances: InstanceMask[];
  surface_type: string;
  model_version: string;
  latency_ms: number;
}

export interface RoadSegmentationBatchRequest {
  dataset_id?: string;
  image_ids?: string[];
  scope?: "remaining" | "all";
  force?: boolean;
  conf_threshold?: number;
  iou_threshold?: number;
}

export interface RoadSegmentationBatchResponse {
  job_id: string;
  total_images: number;
  skipped: number;
}

export interface PrelabelBatchRequest {
  dataset_id: string;
  image_ids?: string[];
  scope?: "remaining" | "all";
  force?: boolean;
  confidence_threshold?: number;
}

export interface BatchJobResponse {
  job_id: string;
  total_images: number;
  skipped: number;
}

export interface BatchJobStatusResponse {
  job_id: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | string;
  progress?: {
    processed: number;
    failed: number;
    skipped: number;
    total: number;
    current: number;
  };
  result?: Record<string, unknown>;
  error?: string;
}

export interface RoadSegmentationBatchRequestLegacy {
  image_ids: string[];
  conf_threshold?: number;
  iou_threshold?: number;
}

export interface RoadAnnotationUpdate {
  instances?: InstanceMask[];
  surface_type?: string;
  reviewed?: boolean;
}

export interface RoadAnnotationResponse {
  id: string;
  annotation_id: string;
  surface_type: string;
  instances: InstanceMask[];
  model_version: string;
  auto_generated: boolean;
  reviewed: boolean;
  created_at: string;
  updated_at: string;
}

export interface RoadClassInfo {
  id: number;
  name: string;
  color: string;
  description: string;
}

export interface RoadClassesResponse {
  classes: RoadClassInfo[];
  version: string;
}

export interface RoadAnalyzeRequest {
  dataset_id: string;
  conf_threshold?: number;
}

export interface RoadConditionReport {
  dataset_id: string;
  total_images: number;
  surface_breakdown: Record<string, number>;
  pothole_count: number;
  pothole_density_per_km2: number;
  crack_severity: 'low' | 'medium' | 'high';
  condition_score: number;
  recommended_action: string | null;
}

export interface RoadSegAnnotation {
  id: string;
  class_id: number;
  class_name: string;
  confidence: number;
  polygon: [number, number][];
  accepted: boolean;
}

// ─── Fleet / Node Types ────────────────────────────────────────────────────

export interface NodeInfo {
  id: string;
  node_id: string;
  district: string;
  latitude: number;
  longitude: number;
  category: string;
  hardware_profile: Record<string, unknown>;
  status: string;
  last_heartbeat_at: string | null;
  is_enabled: boolean;
  created_at: string;
}

export interface HeartbeatTelemetry {
  battery_voltage: number;
  solar_input_watts: number;
  cpu_temp_celsius: number;
  storage_used_gb: number;
  storage_total_gb: number;
  lte_rssi_dbm: number;
  camera_status: string;
  events_captured: number;
  events_uploaded: number;
  bandwidth_mbps: number;
  raw_diagnostics: Record<string, unknown>;
}

export interface NodeAlert {
  node_id: string;
  node_name: string;
  alert: string;
  severity: "info" | "warning" | "critical";
  timestamp: string;
}

// ─── Agricultural Types ────────────────────────────────────────────────────

export interface AgriClassInfo {
  id: number;
  name: string;
  color: string;
  description: string;
}

export interface AgriClassesResponse {
  classes: AgriClassInfo[];
  version: string;
}

export interface AgriAnalyzeRequest {
  dataset_id: string;
  conf_threshold?: number;
}

export interface AgriAnalysisReport {
  dataset_id: string;
  total_images: number;
  crop_breakdown: Record<string, number>;
  health_breakdown: Record<string, number>;
  health_score: number;
  weed_pressure: 'low' | 'medium' | 'high';
  pest_risk: 'low' | 'medium' | 'high';
  recommended_action: string | null;
}

export interface AgriSegmentationRequest {
  image_id: string;
  conf_threshold?: number;
  iou_threshold?: number;
  return_polygons?: boolean;
}

export interface AgriSegmentationResponse {
  image_id: string;
  instances: InstanceMask[];
  crop_type: string;
  health_status: string;
  model_version: string;
  latency_ms: number;
}
