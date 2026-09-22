import { useState, useRef, useEffect, useCallback } from "react";
import { captureFrame, isVideoReady, ReusableFrameCapture } from "../utils/captureFrame";
import { getWSBase } from "../utils/cameraManager";
import { orientationFromMirror } from "../utils/orientation";
import { queueLiveFrame } from "./useOfflineSync";
import { detectAllSeg } from "../ai/yoloSeg";
import { onnxManager } from "../ai/onnxManager";
import * as ort from "onnxruntime-web";
import { yoloClassToTaxonomy } from "../ai/taxonomyMapping";

const LIVE_ONDEVICE_SEG =
  import.meta.env.VITE_ENABLE_LIVE_ONDEVICE_SEG === "true";

export type SaveFrameResult = {
  id: string;
  queued?: boolean;
  annotation_id?: string;
  image_index?: number;
  dataset_id?: string | null;
  ai_draft?: boolean;
};

export interface LiveAnnotation {
  class_name: string;
  taxonomy_label?: string;
  confidence: number;
  bbox: [number, number, number, number];
  track_id?: number;
  mask?: number[][];
  mask_format?: "polygon" | "rle" | null;
  distance_m?: number;
  distance_quality?: string;
  bbox_3d?: {
    corners: number[][];
    dimensions?: [number, number, number];
    yaw?: number;
    yaw_source?: string;
    distance_quality?: string;
    limitation?: string;
    depth_available?: boolean;
  };
  engine?: string;
}

export interface LiveAnnotationResult {
  annotations: LiveAnnotation[];
  inference_ms: number;
  model_type: string;
  timestamp: string;
  warning?: string;
  error?: string;
  detail?: string;
  frame_width?: number;
  frame_height?: number;
  depth_available?: boolean;
  dropped?: boolean;
  busy?: boolean;
  type?: string;
  event?: LiveEvent;
  event_id?: string;
  frames?: number;
  storage_keys?: string[];
}

export interface LiveEvent {
  event_id: string;
  event_type: string;
  rule_id: string;
  rule_name: string;
  track_id: number | null;
  class_name: string | null;
  confidence: number;
  triggered_at: number;
  duration_seconds: number | null;
  auto_saved?: boolean;
  details?: Record<string, unknown>;
}

interface UseLiveAnnotationOptions {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  enabled: boolean;
  modelType?: string;
  mirrored?: boolean;
  fps?: number;
  quality?: number;
  maxWidth?: number;
  eventsEnabled?: boolean;
  autoSave?: boolean;
  datasetId?: string | null;
}

const LATENCY_THRESHOLD_MS = 1000;
const MIN_FPS = 2;
const MAX_FPS = 4;

export function useLiveAnnotation({
  videoRef,
  enabled,
  modelType = "object_detection",
  mirrored = false,
  fps: initialFps = 3,
  quality = 0.85,
  maxWidth = 512,
  eventsEnabled = true,
  autoSave = false,
  datasetId = null,
}: UseLiveAnnotationOptions) {
  const [annotations, setAnnotations] = useState<LiveAnnotation[]>([]);
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [isInferencing, setIsInferencing] = useState(false);
  const [lastInferenceMs, setLastInferenceMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [frameSize, setFrameSize] = useState<{ width: number; height: number } | null>(null);
  const [depthAvailable, setDepthAvailable] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const inferencingRef = useRef(false);
  const pendingSendRef = useRef(false);
  const mirroredRef = useRef(mirrored);
  const eventsEnabledRef = useRef(eventsEnabled);
  const autoSaveRef = useRef(autoSave);
  const datasetIdRef = useRef(datasetId);
  const [onDevice, setOnDevice] = useState(false);

  useEffect(() => {
    mirroredRef.current = mirrored;
  }, [mirrored]);

  useEffect(() => {
    eventsEnabledRef.current = eventsEnabled;
  }, [eventsEnabled]);

  useEffect(() => {
    autoSaveRef.current = autoSave;
  }, [autoSave]);

  useEffect(() => {
    datasetIdRef.current = datasetId;
  }, [datasetId]);

  const effectiveFps =
    lastInferenceMs > LATENCY_THRESHOLD_MS
      ? MIN_FPS
      : lastInferenceMs > 0 && lastInferenceMs <= LATENCY_THRESHOLD_MS
        ? Math.min(initialFps, MAX_FPS)
        : initialFps;

  const getToken = useCallback(() => {
    return localStorage.getItem("studio_token") || "";
  }, []);

  useEffect(() => {
    const run = async () => {
      if (!enabled) {
        setAnnotations([]);
        setLiveEvents([]);
        setError(null);
        setDepthAvailable(false);
        setOnDevice(false);
        return;
      }

      if (modelType === "text_detection" && mirrored) {
        setError("OCR requires un-mirrored frames — disable Mirror preview");
        return;
      }

      const token = getToken();
      if (!token) {
        setError("Not authenticated");
        return;
      }

      const wsBase = getWSBase();
      const params = new URLSearchParams({ model_type: modelType, token });
      if (eventsEnabledRef.current) params.set("events", "1");
      if (autoSaveRef.current && datasetIdRef.current) {
        params.set("auto_save", "1");
        params.set("dataset_id", datasetIdRef.current);
      }
      const ws = new WebSocket(`${wsBase}/ws/annotate/live?${params.toString()}`);
      ws.binaryType = "arraybuffer";
      setOnDevice(false);

      ws.onopen = () => {
        setError(null);
      };

      ws.onmessage = (event) => {
        try {
          const result: LiveAnnotationResult = JSON.parse(event.data);
          if (result.type === "event" && result.event?.event_id) {
            const ev = { ...result.event, auto_saved: false };
            setLiveEvents((prev) => [ev, ...prev.filter((e) => e.event_id !== ev.event_id)].slice(0, 50));
            return;
          }
          if (result.type === "event_saved" && result.event_id) {
            const ev = {
              event_id: result.event_id,
              event_type: result.event?.event_type ?? "rule",
              rule_id: result.event?.rule_id ?? "",
              rule_name: result.event?.rule_name ?? "Rule triggered",
              track_id: result.event?.track_id ?? null,
              class_name: result.event?.class_name ?? null,
              confidence: result.event?.confidence ?? 0,
              triggered_at: result.event?.triggered_at ?? 0,
              duration_seconds: result.event?.duration_seconds ?? null,
              auto_saved: true,
              details: result.event?.details,
            } satisfies LiveEvent;
            setLiveEvents((prev) => [ev, ...prev.filter((e) => e.event_id !== ev.event_id)].slice(0, 50));
            return;
          }
          if (result.error) {
            setError(result.error);
            inferencingRef.current = false;
            pendingSendRef.current = false;
            setIsInferencing(false);
            return;
          }
          if (result.dropped || result.busy) {
            pendingSendRef.current = false;
            return;
          }
          setAnnotations(result.annotations || []);
          setLastInferenceMs(result.inference_ms || 0);
          setDepthAvailable(result.depth_available ?? false);
          if (result.frame_width && result.frame_height) {
            setFrameSize({ width: result.frame_width, height: result.frame_height });
          }
          inferencingRef.current = false;
          pendingSendRef.current = false;
          setIsInferencing(false);
        } catch {
          setError("Failed to parse annotation result");
          inferencingRef.current = false;
          pendingSendRef.current = false;
          setIsInferencing(false);
        }
      };

      ws.onerror = () => {
        setError("WebSocket connection error");
      };

      ws.onclose = () => {
        inferencingRef.current = false;
        pendingSendRef.current = false;
        setIsInferencing(false);
        if (LIVE_ONDEVICE_SEG) {
          setOnDevice(true);
          setError("WebSocket disconnected — on-device segmentation available");
        }
      };

      wsRef.current = ws;
      const frameCapture = new ReusableFrameCapture();

      const tick = async () => {
        const video = videoRef.current;
        if (!video || !isVideoReady(video)) return;

        if (inferencingRef.current || pendingSendRef.current) {
          return;
        }

        const wsConn = wsRef.current;
        if (wsConn && wsConn.readyState === WebSocket.OPEN) {
          inferencingRef.current = true;
          pendingSendRef.current = true;
          setIsInferencing(true);

          try {
            const blob = await frameCapture.capture(video, maxWidth, quality, mirroredRef.current);
            wsConn.send(blob);
          } catch {
            inferencingRef.current = false;
            pendingSendRef.current = false;
            setIsInferencing(false);
          }
        } else if (LIVE_ONDEVICE_SEG && modelType === "object_detection") {
          inferencingRef.current = true;
          setIsInferencing(true);
          try {
            const blob = await frameCapture.capture(video, maxWidth, quality, mirroredRef.current);
            await runOnDeviceSeg(blob, setAnnotations, setLastInferenceMs, setDepthAvailable);
          } finally {
            inferencingRef.current = false;
            setIsInferencing(false);
          }
        }
      };

      intervalRef.current = setInterval(() => void tick(), 1000 / effectiveFps);
    };
    void run();
    return () => {
      clearInterval(intervalRef.current);
      inferencingRef.current = false;
      pendingSendRef.current = false;
      setIsInferencing(false);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [enabled, modelType, mirrored, effectiveFps, quality, maxWidth, videoRef, getToken]);

  const saveFrame = useCallback(async (datasetId?: string): Promise<SaveFrameResult | null> => {
    const video = videoRef.current;
    if (!video || !isVideoReady(video)) return null;

    const token = getToken();
    if (!token) return null;

    const orientation = orientationFromMirror(mirroredRef.current);
    const maskPayload = annotations.map((a) => a.mask ?? null);
    const bbox3dPayload = annotations.map((a) => a.bbox_3d ?? null);

    try {
      const blob = await captureFrame(video, 0.92, "image/jpeg", mirroredRef.current);
      const formData = new FormData();
      formData.append("file", blob, `live_${Date.now()}.jpg`);
      formData.append("annotations", JSON.stringify(annotations));
      formData.append("orientation", orientation);
      formData.append("depth_available", String(depthAvailable));
      if (maskPayload.some(Boolean)) {
        formData.append("masks", JSON.stringify(maskPayload));
      }
      if (bbox3dPayload.some(Boolean)) {
        formData.append("bbox_3d", JSON.stringify(bbox3dPayload));
      }
      if (datasetId) formData.append("dataset_id", datasetId);

      if (!navigator.onLine) {
        await queueLiveFrame(datasetId, blob, annotations, orientation, maskPayload, bbox3dPayload);
        return { id: "queued", queued: true };
      }

      const resp = await fetch("/api/v1/annotations/live", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Save failed" }));
        throw new Error(err.detail || "Save failed");
      }

      return await resp.json() as SaveFrameResult;
    } catch (err) {
      const offline =
        !navigator.onLine ||
        err instanceof TypeError ||
        (err instanceof Error &&
          (err.message === "Failed to fetch" || err.message.includes("Network")));
      if (offline) {
        try {
          const blob = await captureFrame(video, 0.92, "image/jpeg", mirroredRef.current);
          await queueLiveFrame(datasetId, blob, annotations, orientation, maskPayload, bbox3dPayload);
          return { id: "queued", queued: true };
        } catch {
          setError(String(err));
          return null;
        }
      }
      setError(String(err));
      return null;
    }
  }, [videoRef, annotations, getToken, depthAvailable]);

  return {
    annotations,
    liveEvents,
    isInferencing,
    lastInferenceMs,
    error,
    saveFrame,
    frameSize,
    depthAvailable,
    effectiveFps,
    onDevice,
  };
}

async function runOnDeviceSeg(
  blob: Blob,
  setAnnotations: (a: LiveAnnotation[]) => void,
  setLastInferenceMs: (ms: number) => void,
  setDepthAvailable: (v: boolean) => void,
): Promise<void> {
  const start = performance.now();
  const bitmap = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

  await onnxManager.loadModel("yolov8n_seg");
  const detections = await detectAllSeg(imageData, async (input) => {
    const tensor = new ort.Tensor("float32", input, [1, 3, 640, 640]);
    const results = await onnxManager.runInference("yolov8n_seg", { images: tensor });
    const keys = Object.keys(results);
    const output0 = results[keys[0]].data as Float32Array;
    const output1 = results[keys[1]].data as Float32Array;
    const dims = results[keys[0]].dims as number[];
    return { output0, output0Dims: dims, output1 };
  });

  const anns: LiveAnnotation[] = detections.map((d) => ({
    class_name: d.className,
    taxonomy_label: yoloClassToTaxonomy(d.className, "road"),
    confidence: d.confidence,
    bbox: [
      d.bbox[0] * canvas.width,
      d.bbox[1] * canvas.height,
      d.bbox[2] * canvas.width,
      d.bbox[3] * canvas.height,
    ],
    mask: d.polygon.length >= 3 ? d.polygon : undefined,
    mask_format: d.polygon.length >= 3 ? "polygon" : null,
    engine: "ondevice",
  }));

  setAnnotations(anns);
  setDepthAvailable(false);
  setLastInferenceMs(Math.round(performance.now() - start));
}
