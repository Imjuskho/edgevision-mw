from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger("edgevision.video_processing")

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".hevc"}
ALLOWED_VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
    "video/hevc",
    "video/x-hevc",
}
DEFAULT_FRAME_INTERVAL_SEC = 1.0
MAX_FRAMES_PER_VIDEO = 120


class VideoProcessingError(ValueError):
    pass


@dataclass
class ExtractedFrame:
    index: int
    timestamp_sec: float
    jpeg_bytes: bytes
    width: int
    height: int


@dataclass
class VideoProbe:
    filename: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration_sec: float
    codec: str | None
    has_depth_track: bool
    device_make: str | None
    device_model: str | None
    notes: list[str]


def is_video_upload(content_type: str | None, filename: str, data: bytes) -> bool:
    if infer_video_mime_type(data):
        return True
    if content_type and content_type.split(";", 1)[0].strip().lower() in ALLOWED_VIDEO_MIME_TYPES:
        return True
    return _extension(filename) in ALLOWED_VIDEO_EXTENSIONS


def infer_video_mime_type(data: bytes) -> str | None:
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand == b"qt  ":
            return "video/quicktime"
        return "video/mp4"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    return None


def probe_video(video_bytes: bytes, filename: str) -> VideoProbe:
    import cv2

    notes: list[str] = []
    has_depth_track = False
    device_make = None
    device_model = None
    codec = None

    with temp_video_file(video_bytes, filename) as path:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise VideoProcessingError("Could not open video file")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
        if fourcc:
            codec = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00") or None
        cap.release()

    duration_sec = (frame_count / fps) if fps > 0 else 0.0

    depth_probe = _probe_apple_depth_metadata(video_bytes, filename)
    has_depth_track = depth_probe.get("has_depth_track", False)
    device_make = depth_probe.get("device_make")
    device_model = depth_probe.get("device_model")
    notes.extend(depth_probe.get("notes", []))

    if not has_depth_track:
        notes.append(
            "No embedded depth/LiDAR track detected. Depth will be estimated from extracted frames when AI pipelines run."
        )

    return VideoProbe(
        filename=filename,
        width=width,
        height=height,
        fps=fps,
        frame_count=frame_count,
        duration_sec=duration_sec,
        codec=codec,
        has_depth_track=has_depth_track,
        device_make=device_make,
        device_model=device_model,
        notes=notes,
    )


def extract_video_frames(
    video_bytes: bytes,
    filename: str,
    *,
    interval_sec: float = DEFAULT_FRAME_INTERVAL_SEC,
    max_frames: int = MAX_FRAMES_PER_VIDEO,
) -> tuple[VideoProbe, list[ExtractedFrame]]:
    import cv2

    probe = probe_video(video_bytes, filename)
    if probe.frame_count <= 0 or probe.fps <= 0:
        raise VideoProcessingError("Video has no readable frames")

    step = max(1, int(round(probe.fps * interval_sec)))
    frames: list[ExtractedFrame] = []

    with temp_video_file(video_bytes, filename) as path:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise VideoProcessingError("Could not open video file for frame extraction")

        # Read sequentially — CAP_PROP_POS_FRAMES seeking is unreliable on iPhone
        # MOV/HEVC and often returns the same frame for every seek position.
        read_idx = 0
        extracted = 0
        while extracted < max_frames:
            ok, bgr = cap.read()
            if not ok or bgr is None:
                break

            if read_idx % step == 0:
                ok_encode, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                if ok_encode:
                    ts = read_idx / probe.fps if probe.fps > 0 else 0.0
                    frames.append(
                        ExtractedFrame(
                            index=extracted,
                            timestamp_sec=ts,
                            jpeg_bytes=encoded.tobytes(),
                            width=bgr.shape[1],
                            height=bgr.shape[0],
                        )
                    )
                    extracted += 1

            read_idx += 1

        cap.release()

    if not frames:
        raise VideoProcessingError("No frames could be extracted from video")

    logger.info(
        "video_frames_extracted",
        filename=filename,
        extracted=len(frames),
        duration_sec=probe.duration_sec,
        has_depth_track=probe.has_depth_track,
    )
    return probe, frames


def _probe_apple_depth_metadata(video_bytes: bytes, filename: str) -> dict:
    """Best-effort probe for Apple auxiliary depth tracks (rare in standard exports)."""
    notes: list[str] = []
    result = {
        "has_depth_track": False,
        "device_make": None,
        "device_model": None,
        "notes": notes,
    }

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        notes.append("ffprobe unavailable; skipping auxiliary depth-track inspection.")
        return result

    with temp_video_file(video_bytes, filename) as path:
        try:
            proc = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_streams",
                    "-show_format",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            notes.append("ffprobe failed while inspecting video metadata.")
            return result

    if proc.returncode != 0 or not proc.stdout.strip():
        notes.append("ffprobe could not read video metadata.")
        return result

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        notes.append("ffprobe returned invalid metadata.")
        return result

    streams = payload.get("streams") or []
    for stream in streams:
        codec_type = (stream.get("codec_type") or "").lower()
        codec_name = (stream.get("codec_name") or "").lower()
        tags = stream.get("tags") or {}
        if codec_type == "video" and codec_name in {"hevc", "h265", "h264", "av1"}:
            result["device_make"] = result["device_make"] or tags.get("com.apple.quicktime.make")
            result["device_model"] = result["device_model"] or tags.get("com.apple.quicktime.model")
        if codec_type == "video" and any(token in codec_name for token in ("depth", "disparity", "daal")):
            result["has_depth_track"] = True

    tags = (payload.get("format") or {}).get("tags") or {}
    result["device_make"] = result["device_make"] or tags.get("com.apple.quicktime.make")
    result["device_model"] = result["device_model"] or tags.get("com.apple.quicktime.model")

    if result["has_depth_track"]:
        notes.append("Embedded depth/disparity track detected; frame extraction uses RGB video stream only.")
    return result


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


@contextmanager
def temp_video_file(video_bytes: bytes, filename: str):
    ext = _extension(filename) or ".mp4"
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tmp.write(video_bytes)
        tmp.flush()
        tmp.close()
        yield tmp.name
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
