"""Unit tests for video processing helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.video_processing import (
    VideoProcessingError,
    extract_video_frames,
    infer_video_mime_type,
    is_video_upload,
)


def test_infer_video_mime_type_detects_mov_and_mp4():
    mov = b"\x00\x00\x00\x14ftypqt  \x00" + b"\x00" * 20
    mp4 = b"\x00\x00\x00\x18ftypisom\x00" + b"\x00" * 20
    assert infer_video_mime_type(mov) == "video/quicktime"
    assert infer_video_mime_type(mp4) == "video/mp4"


def test_is_video_upload_accepts_empty_mime_with_mov_extension():
    data = b"\x00\x00\x00\x18ftypisom\x00" + b"\x00" * 20
    assert is_video_upload("", "clip.MOV", data) is True


@patch("app.services.video_processing.probe_video")
@patch("cv2.VideoCapture")
@patch("cv2.imencode")
def test_extract_video_frames_returns_jpeg_frames(mock_imencode, mock_capture_cls, mock_probe):
    mock_probe.return_value = MagicMock(
        filename="clip.mov",
        width=64,
        height=48,
        fps=2.0,
        frame_count=4,
        duration_sec=2.0,
        codec="mp4v",
        has_depth_track=False,
        device_make="Apple",
        device_model="iPhone15,3",
        notes=["note"],
    )

    frame = np.full((48, 64, 3), 120, dtype=np.uint8)
    encoded = MagicMock()
    encoded.tobytes.return_value = b"jpeg-bytes"

    mock_imencode.return_value = (True, encoded)

    cap = MagicMock()
    cap.isOpened.return_value = True
    # Sequential read: four frames, then EOF (step=2 at 2fps → 2 extracted)
    cap.read.side_effect = [
        (True, frame),
        (True, frame),
        (True, frame),
        (True, frame),
        (False, None),
    ]
    mock_capture_cls.return_value = cap

    probe, frames = extract_video_frames(b"fake-video", "clip.mov", interval_sec=1.0, max_frames=2)

    assert probe.device_make == "Apple"
    assert len(frames) == 2
    assert frames[0].jpeg_bytes == b"jpeg-bytes"
    assert cap.set.call_count == 0


@patch("app.services.video_processing.probe_video")
def test_extract_video_frames_raises_when_no_frames(mock_probe):
    mock_probe.return_value = MagicMock(
        filename="clip.mov",
        width=64,
        height=48,
        fps=0.0,
        frame_count=0,
        duration_sec=0.0,
        codec=None,
        has_depth_track=False,
        device_make=None,
        device_model=None,
        notes=[],
    )

    with pytest.raises(VideoProcessingError, match="no readable frames"):
        extract_video_frames(b"fake-video", "clip.mov")
