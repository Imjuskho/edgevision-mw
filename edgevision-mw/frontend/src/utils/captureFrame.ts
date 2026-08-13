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
