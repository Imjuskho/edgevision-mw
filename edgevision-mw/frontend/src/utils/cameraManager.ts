let activeStream: MediaStream | null = null;

export async function acquireCamera(
  constraints?: MediaStreamConstraints,
): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Camera access requires HTTPS or localhost.");
  }
  if (activeStream) {
    activeStream.getTracks().forEach((t) => t.stop());
  }
  activeStream = await navigator.mediaDevices.getUserMedia(
    constraints || {
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "environment" },
      audio: false,
    },
  );
  return activeStream;
}

export function releaseCamera(): void {
  if (activeStream) {
    activeStream.getTracks().forEach((t) => t.stop());
    activeStream = null;
  }
}

export async function acquireScreen(
  video?: boolean | { width?: number; height?: number; frameRate?: number },
): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getDisplayMedia) {
    throw new Error("Screen sharing requires HTTPS or localhost.");
  }
  if (activeStream) {
    activeStream.getTracks().forEach((t) => t.stop());
  }
  activeStream = (await navigator.mediaDevices.getDisplayMedia({
    video: video ?? true,
    audio: false,
  })) as MediaStream;
  return activeStream;
}

export function getWSBase(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}`;
}
