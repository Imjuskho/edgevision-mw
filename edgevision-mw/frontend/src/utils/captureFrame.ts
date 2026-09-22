import { mirrorFrame } from "./orientation";

export function isVideoReady(video: HTMLVideoElement): boolean {
  return video.readyState >= 2
    && video.videoWidth > 0
    && video.videoHeight > 0
    && !video.paused;
}

export function captureFrame(
  video: HTMLVideoElement,
  quality = 0.92,
  type: "image/jpeg" | "image/png" = "image/jpeg",
  mirror = false,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    if (!isVideoReady(video)) {
      reject(new Error("Video not ready"));
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      reject(new Error("No 2D context"));
      return;
    }

    if (mirror) {
      mirrorFrame(ctx, canvas.width, video);
    } else {
      ctx.drawImage(video, 0, 0);
    }
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Canvas toBlob returned null"));
    }, type, quality);
  });
}

export async function resizeImageBlob(
  blob: Blob,
  maxWidth: number,
  quality = 0.85,
): Promise<Blob> {
  const img = await createImageBitmap(blob);
  const scale = Math.min(1, maxWidth / img.width);
  const w = Math.round(img.width * scale);
  const h = Math.round(img.height * scale);

  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("No 2D context");

  ctx.drawImage(img, 0, 0, w, h);
  img.close();

  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => {
      if (b) resolve(b);
      else reject(new Error("resizeImageBlob: toBlob returned null"));
    }, "image/jpeg", quality);
  });
}

/**
 * Single-pass capture: mirror + resize + JPEG encode in one canvas draw.
 * Eliminates the old two-step pipeline (captureFrame → resizeImageBlob)
 * which performed 2 JPEG encodes + 1 JPEG decode per frame.
 */
export function captureFrameResized(
  video: HTMLVideoElement,
  maxWidth: number,
  quality = 0.85,
  mirror = false,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    if (!isVideoReady(video)) {
      reject(new Error("Video not ready"));
      return;
    }

    const srcW = video.videoWidth;
    const srcH = video.videoHeight;
    const scale = Math.min(1, maxWidth / srcW);
    const dstW = Math.round(srcW * scale);
    const dstH = Math.round(srcH * scale);

    const canvas = document.createElement("canvas");
    canvas.width = dstW;
    canvas.height = dstH;
    const ctx = canvas.getContext("2d", { willReadFrequently: false });
    if (!ctx) {
      reject(new Error("No 2D context"));
      return;
    }

    if (mirror) {
      ctx.save();
      ctx.translate(dstW, 0);
      ctx.scale(-1, 1);
      ctx.drawImage(video, 0, 0, dstW, dstH);
      ctx.restore();
    } else {
      ctx.drawImage(video, 0, 0, dstW, dstH);
    }

    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("captureFrameResized: toBlob returned null"));
    }, "image/jpeg", quality);
  });
}

/**
 * Persistent offscreen canvas for high-frequency capture.
 * Reuses the same canvas + context across frames instead of allocating per tick.
 */
export class ReusableFrameCapture {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D | null;
  private lastW = 0;
  private lastH = 0;

  constructor() {
    this.canvas = document.createElement("canvas");
    this.ctx = this.canvas.getContext("2d", { willReadFrequently: false });
  }

  capture(
    video: HTMLVideoElement,
    maxWidth: number,
    quality = 0.85,
    mirror = false,
  ): Promise<Blob> {
    return new Promise((resolve, reject) => {
      if (!isVideoReady(video)) {
        reject(new Error("Video not ready"));
        return;
      }
      if (!this.ctx) {
        reject(new Error("No 2D context"));
        return;
      }

      const srcW = video.videoWidth;
      const srcH = video.videoHeight;
      const scale = Math.min(1, maxWidth / srcW);
      const dstW = Math.round(srcW * scale);
      const dstH = Math.round(srcH * scale);

      if (dstW !== this.lastW || dstH !== this.lastH) {
        this.canvas.width = dstW;
        this.canvas.height = dstH;
        this.lastW = dstW;
        this.lastH = dstH;
      } else {
        this.ctx.clearRect(0, 0, dstW, dstH);
      }

      if (mirror) {
        this.ctx.save();
        this.ctx.translate(dstW, 0);
        this.ctx.scale(-1, 1);
        this.ctx.drawImage(video, 0, 0, dstW, dstH);
        this.ctx.restore();
      } else {
        this.ctx.drawImage(video, 0, 0, dstW, dstH);
      }

      this.canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error("ReusableFrameCapture: toBlob returned null"));
      }, "image/jpeg", quality);
    });
  }

  dispose() {
    this.ctx = null;
    this.canvas.width = 0;
    this.canvas.height = 0;
  }
}
