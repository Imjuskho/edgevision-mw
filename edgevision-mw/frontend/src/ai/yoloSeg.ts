/**
 * Browser-side YOLOv8-seg postprocessing (ported from app/ai/yolo_seg.py).
 * Pure JS — no opencv.js.
 */

const COCO_NAMES = [
  "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
  "truck", "boat", "traffic light", "fire hydrant", "stop sign",
  "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
];

export interface SegDetection {
  className: string;
  confidence: number;
  bbox: [number, number, number, number];
  polygon: [number, number][];
}

const CONF_THRESHOLD = 0.35;
const IOU_THRESHOLD = 0.45;
const INPUT_SIZE = 640;
const MAX_MASK_POINTS = 32;

function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x));
}

function iou(a: number[], b: number[]): number {
  const x1 = Math.max(a[0], b[0]);
  const y1 = Math.max(a[1], b[1]);
  const x2 = Math.min(a[0] + a[2], b[0] + b[2]);
  const y2 = Math.min(a[1] + a[3], b[1] + b[3]);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const areaA = a[2] * a[3];
  const areaB = b[2] * b[3];
  const union = areaA + areaB - inter;
  return union === 0 ? 0 : inter / union;
}

function nms(
  boxes: number[][],
  scores: number[],
  threshold: number,
): number[] {
  const order = scores
    .map((s, i) => [s, i] as const)
    .sort((a, b) => b[0] - a[0])
    .map(([, i]) => i);
  const keep: number[] = [];
  const suppressed = new Set<number>();

  for (const i of order) {
    if (suppressed.has(i)) continue;
    keep.push(i);
    for (const j of order) {
      if (j === i || suppressed.has(j)) continue;
      if (iou(boxes[i], boxes[j]) > threshold) suppressed.add(j);
    }
  }
  return keep;
}

function extractPolygonFromMask(
  mask: Float32Array,
  maskW: number,
  maskH: number,
  origW: number,
  origH: number,
  bx1: number,
  by1: number,
  bx2: number,
  by2: number,
): [number, number][] {
  // Marching-squares-lite: collect boundary points above threshold
  const threshold = 0.5;
  const points: [number, number][] = [];
  for (let y = 0; y < maskH; y++) {
    for (let x = 0; x < maskW; x++) {
      const v = mask[y * maskW + x];
      const px = (x / maskW) * origW;
      const py = (y / maskH) * origH;
      if (v > threshold && px >= bx1 && px <= bx2 && py >= by1 && py <= by2) {
        if (x === 0 || x === maskW - 1 || y === 0 || y === maskH - 1 ||
            mask[y * maskW + x - 1] <= threshold ||
            mask[y * maskW + x + 1] <= threshold ||
            mask[(y - 1) * maskW + x] <= threshold ||
            mask[(y + 1) * maskW + x] <= threshold) {
          points.push([px / origW, py / origH]);
        }
      }
    }
  }
  if (points.length < 3) return [];
  // Downsample to max points
  if (points.length > MAX_MASK_POINTS) {
    const step = Math.ceil(points.length / MAX_MASK_POINTS);
    return points.filter((_, i) => i % step === 0).slice(0, MAX_MASK_POINTS);
  }
  return points;
}

function preprocessImageData(imageData: ImageData): {
  blob: Float32Array;
  padX: number;
  padY: number;
  scale: number;
} {
  const { width: w, height: h, data } = imageData;
  const scale = Math.min(INPUT_SIZE / w, INPUT_SIZE / h);
  const nw = Math.round(w * scale);
  const nh = Math.round(h * scale);
  const padX = Math.floor((INPUT_SIZE - nw) / 2);
  const padY = Math.floor((INPUT_SIZE - nh) / 2);

  const blob = new Float32Array(3 * INPUT_SIZE * INPUT_SIZE);
  blob.fill(114 / 255);

  for (let y = 0; y < nh; y++) {
    for (let x = 0; x < nw; x++) {
      const srcX = Math.min(w - 1, Math.round(x / scale));
      const srcY = Math.min(h - 1, Math.round(y / scale));
      const srcIdx = (srcY * w + srcX) * 4;
      const dstY = padY + y;
      const dstX = padX + x;
      for (let c = 0; c < 3; c++) {
        blob[c * INPUT_SIZE * INPUT_SIZE + dstY * INPUT_SIZE + dstX] =
          data[srcIdx + c] / 255;
      }
    }
  }
  return { blob, padX, padY, scale };
}

export function postprocessYoloSeg(
  output0: Float32Array,
  output0Dims: number[],
  output1: Float32Array,
  origW: number,
  origH: number,
  padX: number,
  padY: number,
  scale: number,
  confThreshold = CONF_THRESHOLD,
  iouThreshold = IOU_THRESHOLD,
): SegDetection[] {
  // output0: [1, 116, 8400] → transpose to [8400, 116]
  const numPreds = output0Dims[2] ?? 8400;
  const featDim = output0Dims[1] ?? 116;

  const boxes: number[][] = [];
  const scores: number[] = [];
  const classIds: number[] = [];
  const coeffsList: Float32Array[] = [];

  for (let i = 0; i < numPreds; i++) {
    let maxScore = 0;
    let maxClass = 0;
    for (let c = 0; c < 80; c++) {
      const s = output0[4 + c + i * featDim];
      if (s > maxScore) {
        maxScore = s;
        maxClass = c;
      }
    }
    if (maxScore < confThreshold) continue;

    const cx = output0[0 + i * featDim];
    const cy = output0[1 + i * featDim];
    const bw = output0[2 + i * featDim];
    const bh = output0[3 + i * featDim];
    boxes.push([cx - bw / 2, cy - bh / 2, bw, bh]);
    scores.push(maxScore);
    classIds.push(maxClass);
    coeffsList.push(output0.slice(84 + i * featDim, 116 + i * featDim));
  }

  if (boxes.length === 0) return [];

  const keep = nms(boxes, scores, iouThreshold);
  const protos = output1; // [32, 160, 160]
  const protoSize = 160;
  const numProtos = 32;

  const results: SegDetection[] = [];

  for (const idx of keep) {
    const [x1, y1, w, h] = boxes[idx];
    const x1Orig = Math.max(0, (x1 - padX) / scale);
    const y1Orig = Math.max(0, (y1 - padY) / scale);
    const wOrig = Math.max(0, Math.min(w / scale, origW - x1Orig));
    const hOrig = Math.max(0, Math.min(h / scale, origH - y1Orig));

    const coeffs = coeffsList[idx];
    const mask160 = new Float32Array(protoSize * protoSize);
    for (let y = 0; y < protoSize; y++) {
      for (let x = 0; x < protoSize; x++) {
        let sum = 0;
        for (let p = 0; p < numProtos; p++) {
          sum += protos[p * protoSize * protoSize + y * protoSize + x] * coeffs[p];
        }
        mask160[y * protoSize + x] = sigmoid(sum);
      }
    }

    const maskFull = new Float32Array(INPUT_SIZE * INPUT_SIZE);
    for (let y = 0; y < INPUT_SIZE; y++) {
      for (let x = 0; x < INPUT_SIZE; x++) {
        const sx = (x / INPUT_SIZE) * protoSize;
        const sy = (y / INPUT_SIZE) * protoSize;
        const x0 = Math.floor(sx);
        const y0 = Math.floor(sy);
        maskFull[y * INPUT_SIZE + x] = mask160[y0 * protoSize + x0];
      }
    }

    const cropH = Math.round(origH * scale);
    const cropW = Math.round(origW * scale);
    const maskCrop = new Float32Array(cropW * cropH);
    for (let y = 0; y < cropH; y++) {
      for (let x = 0; x < cropW; x++) {
        const sx = padX + x;
        const sy = padY + y;
        if (sx >= 0 && sx < INPUT_SIZE && sy >= 0 && sy < INPUT_SIZE) {
          maskCrop[y * cropW + x] = maskFull[sy * INPUT_SIZE + sx];
        }
      }
    }

    const maskOrig = new Float32Array(origW * origH);
    for (let y = 0; y < origH; y++) {
      for (let x = 0; x < origW; x++) {
        const cx2 = Math.min(cropW - 1, Math.round(x * scale));
        const cy2 = Math.min(cropH - 1, Math.round(y * scale));
        maskOrig[y * origW + x] = maskCrop[cy2 * cropW + cx2];
      }
    }

    const bx1 = x1Orig;
    const by1 = y1Orig;
    const bx2 = x1Orig + wOrig;
    const by2 = y1Orig + hOrig;

    const polygon = extractPolygonFromMask(
      maskOrig, origW, origH, origW, origH, bx1, by1, bx2, by2,
    );

    const className = COCO_NAMES[classIds[idx]] ?? `class_${classIds[idx]}`;
    results.push({
      className,
      confidence: scores[idx],
      bbox: [
        x1Orig / origW,
        y1Orig / origH,
        wOrig / origW,
        hOrig / origH,
      ],
      polygon,
    });
  }

  return results;
}

export async function detectAllSeg(
  imageData: ImageData,
  runInference: (input: Float32Array) => Promise<{ output0: Float32Array; output0Dims: number[]; output1: Float32Array }>,
): Promise<SegDetection[]> {
  const { blob, padX, padY, scale } = preprocessImageData(imageData);
  const { output0, output0Dims, output1 } = await runInference(blob);
  return postprocessYoloSeg(
    output0,
    output0Dims,
    output1,
    imageData.width,
    imageData.height,
    padX,
    padY,
    scale,
  );
}

export function imageDataToSegTensor(blob: Float32Array): Float32Array {
  return blob;
}
