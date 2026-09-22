import { useState, useRef, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { captureFrame, isVideoReady } from "../utils/captureFrame";
import { loadMirrorPreference, saveMirrorPreference } from "../utils/orientation";
import type { LiveAnnotation } from "../hooks/useLiveAnnotation";
import AnnotationOverlay from "./AnnotationOverlay";

interface Props {
  onCapture: (blob: Blob, filename: string) => void;
  capturedCount: number;
  onAnnotations?: LiveAnnotation[];
}

export default function CameraCapture({ onCapture, capturedCount, onAnnotations }: Props) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [permDenied, setPermDenied] = useState(false);
  const [facingMode, setFacingMode] = useState<"user" | "environment">("user");
  const [mirrored, setMirrored] = useState(() => loadMirrorPreference());
  const [videoSize, setVideoSize] = useState({ width: 640, height: 480 });

  const handleVideoMetadata = () => {
    const v = videoRef.current;
    if (v?.videoWidth) setVideoSize({ width: v.videoWidth, height: v.videoHeight });
  };

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setActive(false);
  }, []);

  const startCamera = useCallback(async () => {
    setError(null);
    setPermDenied(false);

    const selectedMode = facingMode;

    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Camera access is not supported in this browser.");
      return;
    }

    try {
      const result = await navigator.permissions.query({ name: "camera" as PermissionName });
      if (result.state === "denied") {
        setPermDenied(true);
        setError("Camera permission is blocked. Go to browser settings > Privacy > Camera and allow access.");
        return;
      }
    } catch {
      // Some browsers don't support querying camera permission
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: selectedMode, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;
      setActive(true);
    } catch (err) {
      const msg = err instanceof DOMException
        ? err.name === "NotAllowedError"
          ? "Camera permission denied. Allow camera access and try again."
          : err.name === "NotFoundError"
            ? "No camera found on this device."
            : `Camera error: ${err.message}`
        : "Failed to start camera";
      setError(msg);
    }
  }, [facingMode]);

  useEffect(() => {
    if (!active || !streamRef.current) return;
    const video = videoRef.current;
    if (!video) return;

    video.srcObject = streamRef.current;
    video.onloadedmetadata = () => {
      video.play().catch(() => {
        /* ignore play failures */
      });
    };
    video.play().catch(() => {
      /* ignore play failures */
    });
  }, [active]);

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
  }, []);

  const snap = useCallback(async () => {
    const video = videoRef.current;
    if (!video || !isVideoReady(video)) return;
    try {
      const blob = await captureFrame(video, 0.92, "image/jpeg", mirrored);
      const ts = Date.now();
      onCapture(blob, `webcam_${ts}.jpg`);
    } catch {
      /* capture failed */
    }
  }, [onCapture, mirrored]);

  const toggleCamera = useCallback(async () => {
    const nextMode = facingMode === "user" ? "environment" : "user";
    stopCamera();
    setFacingMode(nextMode);
    await startCamera();
  }, [facingMode, startCamera, stopCamera]);

  const handleMirrorToggle = useCallback(() => {
    setMirrored((prev) => {
      const next = !prev;
      saveMirrorPreference(next);
      return next;
    });
  }, []);

  const videoWidth = videoSize.width;
  const videoHeight = videoSize.height;

  return (
    <div className="camera-capture">
      {error && (
        <div className="upload-note upload-note--error">
          {error}
          {permDenied && (
            <div className="perm-denied-link">
              <a href="https://support.google.com/chrome/answer/2693767" target="_blank" rel="noopener noreferrer">
                How to reset camera permissions
              </a>
            </div>
          )}
        </div>
      )}

      {!active ? (
        <div className="camera-start">
          <button className="btn btn-primary" onClick={startCamera}>
            Open Camera
          </button>
          <span className="upload-note upload-note--block">
            {t("upload.cameraNote", "Capture photos directly from your camera")}
          </span>
        </div>
      ) : (
        <div className="camera-live">
          <div className="camera-video-wrapper">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              onLoadedMetadata={handleVideoMetadata}
              className={`camera-video${mirrored ? " camera-video-mirror" : ""}`}
            />
            {onAnnotations && onAnnotations.length > 0 && (
              <AnnotationOverlay
                annotations={onAnnotations}
                videoWidth={videoWidth}
                videoHeight={videoHeight}
                previewMirrored={mirrored}
              />
            )}
          </div>

          <div className="camera-controls">
            <button className="btn btn-primary camera-snap" onClick={snap}>
              Capture
            </button>
            <button className="btn" onClick={toggleCamera}>
              Flip
            </button>
            <label className="live-annotate-toggle live-annotate-toggle-spaced">
              <input type="checkbox" checked={mirrored} onChange={handleMirrorToggle} />
              {t("liveAnnotate.mirrorPreview", "Mirror preview")}
            </label>
            <button className="btn" onClick={stopCamera}>
              Close
            </button>
          </div>

          {capturedCount > 0 && (
            <div className="upload-note upload-note--center">
              {capturedCount} image{capturedCount !== 1 ? "s" : ""} captured
            </div>
          )}
        </div>
      )}
    </div>
  );
}
