import { useState, useRef, useEffect, useCallback } from "react";
import { captureFrame, isVideoReady, resizeImageBlob } from "../utils/captureFrame";
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
}

interface UseLiveAnnotationOptions {
  videoRef: React.RefObject<HTMLVideoElement>;
  enabled: boolean;
  modelType?: string;
  mirrored?: boolean;
  fps?: number;
  quality?: number;
  maxWidth?: number;
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
}: UseLiveAnnotationOptions) {
  const [annotations, setAnnotations] = useState<LiveAnnotation[]>([]);
  const [isInferencing, setIsInferencing] = useState(false);
  const [lastInferenceMs, setLastInferenceMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [frameSize, setFrameSize] = useState<{ width: number; height: number } | null>(null);
  const [depthAvailable, setDepthAvailable] = useState(false);
  const [effectiveFps, setEffectiveFps] = useState(initialFps);
  const wsRef = useRef<WebSocket | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval>>();
  const inferencingRef = useRef(false);
  const pendingSendRef = useRef(false);
  const mirroredRef = useRef(mirrored);
  const onDeviceRef = useRef(false);

  useEffect(() => {
    mirroredRef.current = mirrored;
  }, [mirrored]);

  useEffect(() => {
    if (lastInferenceMs > LATENCY_THRESHOLD_MS) {
      setEffectiveFps(MIN_FPS);
    } else if (lastInferenceMs > 0 && lastInferenceMs <= LATENCY_THRESHOLD_MS) {
      setEffectiveFps(Math.min(initialFps, MAX_FPS));
    }
  }, [lastInferenceMs, initialFps]);

  const getToken = useCallback(() => {
    return localStorage.getItem("studio_token") || "";
  }, []);

  useEffect(() => {
    if (!enabled) {
      setAnnotations([]);
      setError(null);
      setDepthAvailable(false);
      onDeviceRef.current = false;
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
    const ws = new WebSocket(`${wsBase}/ws/annotate/live?model_type=${encodeURIComponent(modelType)}&token=${encodeURIComponent(token)}`);
    ws.binaryType = "arraybuffer";
    onDeviceRef.current = false;

    ws.onopen = () => {
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const result: LiveAnnotationResult = JSON.parse(event.data);
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
        onDeviceRef.current = true;
        setError("WebSocket disconnected — on-device segmentation available");
      }
    };

    wsRef.current = ws;

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
          const blob = await captureFrame(video, quality, "image/jpeg", mirroredRef.current);
          const resized = await resizeImageBlob(blob, maxWidth, quality);
          const buffer = await resized.arrayBuffer();
          wsConn.send(buffer);
        } catch {
          inferencingRef.current = false;
          pendingSendRef.current = false;
          setIsInferencing(false);
        }
      } else if (LIVE_ONDEVICE_SEG && modelType === "object_detection") {
        inferencingRef.current = true;
        setIsInferencing(true);
        try {
          const blob = await captureFrame(video, quality, "image/jpeg", mirroredRef.current);
          const resized = await resizeImageBlob(blob, maxWidth, quality);
          await runOnDeviceSeg(resized, setAnnotations, setLastInferenceMs, setDepthAvailable);
        } finally {
          inferencingRef.current = false;
          setIsInferencing(false);
        }
      }
    };

    intervalRef.current = setInterval(() => void tick(), 1000 / effectiveFps);

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
    isInferencing,
    lastInferenceMs,
    error,
    saveFrame,
    frameSize,
    depthAvailable,
    effectiveFps,
    onDevice: onDeviceRef.current,
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
