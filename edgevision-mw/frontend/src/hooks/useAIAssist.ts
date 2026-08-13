import { useCallback, useState } from 'react';
import * as ort from 'onnxruntime-web';
import { onnxManager } from '../ai/onnxManager';
import { detectAllSeg } from '../ai/yoloSeg';
import { yoloClassToTaxonomy, classifyAgriByColor } from '../ai/taxonomyMapping';
import type { BBox } from '../types';

type TaxonomyContext = "road" | "agri";

interface Point {
  x: number;
  y: number;
}

interface UseAIAssistReturn {
  isModelLoading: boolean;
  loadProgress: number;
  isInferencing: boolean;
  lastError: string | null;
  modelUsed: string | null;
  modelStatus: Record<string, string>;
  aiAssistClick: (clickPoint: Point, imageData: ImageData) => Promise<BBox | null>;
  aiDetectAll: (imageData: ImageData) => Promise<BBox[]>;
  initModels: () => Promise<void>;
}

const CLASS_NAMES = [
  'car', 'matola', 'pedestrian', 'bicycle', 'motorcycle',
  'goat', 'cow', 'dog', 'bus', 'minibus'
];

let annotationIdCounter = 0;
function nextAnnotationId(): string {
  annotationIdCounter += 1;
  return `ann_${Date.now()}_${annotationIdCounter}`;
}

function attachFabricMeta(box: BBox, annotationId: string): BBox {
  return { ...box, annotationId };
}

export function useAIAssist(taxonomyContext: TaxonomyContext = "road"): UseAIAssistReturn {
  const [isModelLoading, setIsModelLoading] = useState(false);
  const [loadProgress, setLoadProgress] = useState(0);
  const [isInferencing, setIsInferencing] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [modelUsed, setModelUsed] = useState<string | null>(null);
  const [modelStatus, setModelStatus] = useState<Record<string, string>>({});

  const setModelState = useCallback((modelKey: string, status: string) => {
    setModelStatus((prev) => ({ ...prev, [modelKey]: status }));
  }, []);

  const initModels = useCallback(async () => {
    setIsModelLoading(true);
    setLastError(null);
    setLoadProgress(0);
    setModelStatus({});
    try {
      await onnxManager.init();

      const models = ['yolov8n_cls', 'yolov8n_seg'];
      for (const modelKey of models) {
        setModelState(modelKey, 'loading');
        try {
          await onnxManager.loadModel(modelKey, (p) => {
            setLoadProgress(p.percent);
          });
          setModelState(modelKey, 'loaded');
        } catch {
          setModelState(modelKey, 'failed');
        }
      }

      if (onnxManager.isLoaded('yolov8n_cls')) {
        setModelUsed('yolov8n_cls');
      }
      setLoadProgress(100);
    } catch (err) {
      setLastError(err instanceof Error ? err.message : 'Model init failed');
      throw err;
    } finally {
      setIsModelLoading(false);
    }
  }, [setModelState]);

  const aiAssistClick = useCallback(
    async (clickPoint: Point, imageData: ImageData): Promise<BBox | null> => {
      setIsInferencing(true);
      setLastError(null);

      try {
        const crop = extractCrop(imageData, clickPoint, 256);
        const clsTensor = imageToTensor(crop, [1, 3, 224, 224]);
        const clsResults = await onnxManager.runInference('yolov8n_cls', { images: clsTensor });
        const outTensor = clsResults.output0 ?? clsResults.output;
        if (!outTensor) { setLastError('Unexpected model output format'); return null; }
        const probs = outTensor.data as Float32Array;
        const { classIdx, confidence } = argmax(probs);

        if (confidence < 0.35) return null;

        const className = CLASS_NAMES[classIdx] || 'car';
        const taxonomyLabel = yoloClassToTaxonomy(className, taxonomyContext);
        setModelUsed('yolov8n_cls');

        const bbox: BBox = {
          x: Math.max(0, clickPoint.x - 0.075),
          y: Math.max(0, clickPoint.y - 0.075),
          width: 0.15,
          height: 0.15,
          label: taxonomyLabel,
          confidence,
          category: taxonomyLabel.split('_')[0],
          engine: 'yolov8n_cls+fallback',
        };

        return attachFabricMeta(bbox, nextAnnotationId());
      } catch (err) {
        setLastError(err instanceof Error ? err.message : 'Inference failed');
        return null;
      } finally {
        setIsInferencing(false);
      }
    },
    [taxonomyContext]
  );

  const runBrowserSeg = useCallback(async (imageData: ImageData): Promise<BBox[]> => {
    await onnxManager.loadModel('yolov8n_seg');
    const detections = await detectAllSeg(imageData, async (input) => {
      const tensor = new ort.Tensor('float32', input, [1, 3, 640, 640]);
      const results = await onnxManager.runInference('yolov8n_seg', { images: tensor });
      const keys = Object.keys(results);
      return {
        output0: results[keys[0]].data as Float32Array,
        output0Dims: results[keys[0]].dims as number[],
        output1: results[keys[1]].data as Float32Array,
      };
    });

    return detections.map((d) => {
      const annId = nextAnnotationId();
      const label = yoloClassToTaxonomy(d.className, taxonomyContext);
      return attachFabricMeta({
        x: d.bbox[0],
        y: d.bbox[1],
        width: d.bbox[2],
        height: d.bbox[3],
        label,
        confidence: d.confidence,
        category: label.split('_')[0],
        polygon: d.polygon.length >= 3 ? d.polygon : undefined,
        engine: 'browser_yolov8n_seg',
      }, annId);
    });
  }, [taxonomyContext]);

  const aiDetectAll = useCallback(
    async (imageData: ImageData): Promise<BBox[]> => {
      setIsInferencing(true);
      setLastError(null);
      const results: BBox[] = [];

      if (taxonomyContext === "agri") {
        const { cropType, healthStatus, confidence } = classifyAgriByColor(imageData);
        const result: BBox = attachFabricMeta({
          x: 0.05, y: 0.05, width: 0.9, height: 0.9,
          label: cropType,
          category: "agricultural",
          confidence,
          attributes: [`health:${healthStatus}`],
          engine: 'agri_color',
        }, nextAnnotationId());
        setIsInferencing(false);
        return [result];
      }

      // 1. Prefer server-side YOLOv8-seg prelabel when online
      try {
        const blob = imageDataToBlob(imageData);
        const token = localStorage.getItem("studio_token");
        if (token && navigator.onLine) {
          const formData = new FormData();
          formData.append("file", blob, "frame.jpg");
          const resp = await fetch("/api/v1/studio/prelabel/image?confidence_threshold=0.35", {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          });
          if (resp.ok) {
            const data = await resp.json();
            const boxes: BBox[] = (data.detections || []).map((d: {
              label: string;
              confidence: number;
              bbox: number[];
              mask?: number[][];
            }) => {
              const annId = nextAnnotationId();
              const box: BBox = {
                x: d.bbox[0],
                y: d.bbox[1],
                width: d.bbox[2],
                height: d.bbox[3],
                label: d.label,
                confidence: d.confidence,
                category: d.label.split("_")[0],
                engine: 'server_yolov8n_seg',
              };
              if (d.mask && d.mask.length >= 3) {
                box.polygon = d.mask.map(([x, y]) => [x, y] as [number, number]);
              }
              return attachFabricMeta(box, annId);
            });
            if (boxes.length > 0) {
              setModelUsed("server_yolov8n_seg");
              setIsInferencing(false);
              return boxes;
            }
          }
        }
      } catch {
        /* fall through to browser seg */
      }

      // 2. Browser YOLOv8-seg
      try {
        const segBoxes = await runBrowserSeg(imageData);
        if (segBoxes.length > 0) {
          setModelUsed('browser_yolov8n_seg');
          setIsInferencing(false);
          return segBoxes;
        }
      } catch {
        /* fall through to cls grid */
      }

      // 3. CLS grid fallback
      try {
        await onnxManager.loadModel('yolov8n_cls');
        setModelUsed('yolov8n_cls');
        const gridStep = 128;
        const cropSize = 224;
        const seen = new Map<string, number>();

        for (let gy = 0; gy < imageData.height; gy += gridStep) {
          for (let gx = 0; gx < imageData.width; gx += gridStep) {
            const cx = gx + gridStep / 2;
            const cy = gy + gridStep / 2;
            const center: Point = { x: cx / imageData.width, y: cy / imageData.height };

            const crop = extractCrop(imageData, center, 256);
            const clsTensor = imageToTensor(crop, [1, 3, 224, 224]);
            const clsResults = await onnxManager.runInference('yolov8n_cls', { images: clsTensor });
            const outTensor = clsResults.output0 ?? clsResults.output;
            if (!outTensor) continue;
            const probs = outTensor.data as Float32Array;
            const { classIdx, confidence } = argmax(probs);

            if (confidence < 0.45) continue;

            const className = CLASS_NAMES[classIdx] || 'car';
            const taxonomyLabel = yoloClassToTaxonomy(className, taxonomyContext);
            const gridKey = `${Math.floor(gx / gridStep)},${Math.floor(gy / gridStep)}`;

            const existingCount = seen.get(gridKey) || 0;
            if (existingCount > 0) continue;
            seen.set(gridKey, existingCount + 1);

            const halfSize = (cropSize / 2) / Math.max(imageData.width, imageData.height);
            const box: BBox = attachFabricMeta({
              x: Math.max(0, center.x - halfSize),
              y: Math.max(0, center.y - halfSize),
              width: halfSize * 2,
              height: halfSize * 2,
              label: taxonomyLabel,
              confidence,
              category: taxonomyLabel.split('_')[0],
              engine: 'grid',
            }, nextAnnotationId());

            results.push(box);
          }
        }

        const merged = mergeOverlappingBoxes(results, 0.15);
        if (merged.length === 0) {
          setLastError("AI_MODELS_UNAVAILABLE");
        }
        return merged;
      } catch (err) {
        setLastError(err instanceof Error ? err.message : 'Detection failed');
        return results;
      } finally {
        setIsInferencing(false);
      }
    },
    [taxonomyContext, runBrowserSeg]
  );

  return {
    isModelLoading,
    loadProgress,
    isInferencing,
    lastError,
    modelUsed,
    modelStatus,
    aiAssistClick,
    aiDetectAll,
    initModels,
  };
}

function imageDataToBlob(imageData: ImageData): Blob {
  const canvas = document.createElement("canvas");
  canvas.width = imageData.width;
  canvas.height = imageData.height;
  canvas.getContext("2d")!.putImageData(imageData, 0, 0);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
  const bin = atob(dataUrl.split(",")[1]);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type: "image/jpeg" });
}

function extractCrop(imageData: ImageData, center: Point, size: number): ImageData {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d')!;

  const srcX = Math.max(0, Math.min(imageData.width - size, Math.round(center.x * imageData.width - size / 2)));
  const srcY = Math.max(0, Math.min(imageData.height - size, Math.round(center.y * imageData.height - size / 2)));

  const srcCanvas = document.createElement('canvas');
  srcCanvas.width = imageData.width;
  srcCanvas.height = imageData.height;
  srcCanvas.getContext('2d')!.putImageData(imageData, 0, 0);

  ctx.drawImage(srcCanvas, srcX, srcY, size, size, 0, 0, size, size);
  return ctx.getImageData(0, 0, size, size);
}

function imageToTensor(imageData: ImageData, dims: number[]): ort.Tensor {
  const { data, width, height } = imageData;
  const floatData = new Float32Array(dims[1] * dims[2] * dims[3]);

  const targetW = dims[3];
  const targetH = dims[2];

  for (let c = 0; c < 3; c++) {
    for (let y = 0; y < targetH; y++) {
      for (let x = 0; x < targetW; x++) {
        const srcX = Math.min(width - 1, Math.round((x / targetW) * width));
        const srcY = Math.min(height - 1, Math.round((y / targetH) * height));
        const srcIdx = (srcY * width + srcX) * 4 + c;
        const dstIdx = c * targetH * targetW + y * targetW + x;
        const mean = [0.485, 0.456, 0.406][c];
        const std = [0.229, 0.224, 0.225][c];
        floatData[dstIdx] = (data[srcIdx] / 255 - mean) / std;
      }
    }
  }

  return new ort.Tensor('float32', floatData, dims);
}

function argmax(arr: Float32Array): { classIdx: number; confidence: number } {
  let maxIdx = 0;
  let maxVal = arr[0];
  for (let i = 1; i < arr.length; i++) {
    if (arr[i] > maxVal) {
      maxVal = arr[i];
      maxIdx = i;
    }
  }
  return { classIdx: maxIdx, confidence: maxVal };
}

function mergeOverlappingBoxes(boxes: BBox[], iouThreshold: number): BBox[] {
  const byClass = new Map<string, BBox[]>();
  for (const box of boxes) {
    const key = box.label;
    if (!byClass.has(key)) byClass.set(key, []);
    byClass.get(key)!.push(box);
  }

  const result: BBox[] = [];
  for (const [, classBoxes] of byClass) {
    const sorted = [...classBoxes].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
    const selected: BBox[] = [];
    for (const box of sorted) {
      const suppressed = selected.some((m) => computeIoU(m, box) > iouThreshold);
      if (!suppressed) selected.push(box);
    }
    result.push(...selected);
  }
  return result;
}

function computeIoU(a: BBox, b: BBox): number {
  const x1 = Math.max(a.x, b.x);
  const y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.width, b.x + b.width);
  const y2 = Math.min(a.y + a.height, b.y + b.height);

  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const areaA = a.width * a.height;
  const areaB = b.width * b.height;
  const union = areaA + areaB - inter;

  return union === 0 ? 0 : inter / union;
}
