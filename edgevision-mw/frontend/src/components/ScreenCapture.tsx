import { useState, useRef, useCallback, useEffect } from "react";
import { isVideoReady } from "../utils/captureFrame";

interface Props {
  onCapture: (blob: Blob, filename: string) => void;
  capturedCount: number;
}

export default function ScreenCapture({ onCapture, capturedCount }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const stopScreenShare = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setActive(false);
    setRecording(false);
  }, []);

  const startScreenShare = useCallback(async () => {
    // Ensure we're in a user gesture context for getDisplayMedia
    setError(null);
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setError("Screen sharing requires HTTPS or localhost.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: false,
      });

      streamRef.current = stream;

      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        stopScreenShare();
      });

      setActive(true);
    } catch (err) {
      const msg = err instanceof DOMException
        ? err.name === "NotAllowedError"
          ? "Screen sharing was cancelled or denied."
          : `Screen capture error: ${err.message}`
        : "Failed to start screen capture";
      setError(msg);
    }
  }, [stopScreenShare]);

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

  const snap = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    if (!isVideoReady(video)) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return;
      const ts = Date.now();
      onCapture(blob, `screen_${ts}.jpg`);
    }, "image/jpeg", 0.92);
  }, [onCapture]);

  const startRecording = useCallback(() => {
    if (!streamRef.current) return;
    chunksRef.current = [];
    const recorder = new MediaRecorder(streamRef.current, {
      mimeType: "video/webm;codecs=vp8,opus",
    });
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: "video/webm" });
      const ts = Date.now();
      onCapture(blob, `screen_recording_${ts}.webm`);
      chunksRef.current = [];
    };
    mediaRecorderRef.current = recorder;
    recorder.start();
    setRecording(true);
  }, [onCapture]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    setRecording(false);
  }, []);

  return (
    <div className="screen-capture">
      {error && (
        <div className="upload-note upload-note--error">
          {error}
        </div>
      )}

      {!active ? (
        <div className="camera-start">
          <button className="btn btn-primary" onClick={startScreenShare}>
            Share Screen
          </button>
          <span className="upload-note upload-note--block">
            Capture screenshots or record your screen
          </span>
        </div>
      ) : (
        <div className="camera-live">
          <video ref={videoRef} autoPlay playsInline muted className="camera-video" />

          <canvas ref={canvasRef} className="hidden-canvas" />

          <div className="camera-controls">
            <button className="btn btn-primary" onClick={snap}>
              Screenshot
            </button>
            {!recording ? (
              <button className="btn btn--record" onClick={startRecording}>
                Record
              </button>
            ) : (
              <button className="btn btn--record-active" onClick={stopRecording}>
                Stop Recording
              </button>
            )}
            <button className="btn" onClick={stopScreenShare}>
              Stop Sharing
            </button>
          </div>

          {recording && (
            <div className="upload-note upload-note--danger">
              Recording...
            </div>
          )}

          {capturedCount > 0 && (
            <div className="upload-note upload-note--center">
              {capturedCount} capture{capturedCount !== 1 ? "s" : ""} taken
            </div>
          )}
        </div>
      )}
    </div>
  );
}
