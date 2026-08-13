#!/usr/bin/env bash
# Download/export YOLO ONNX models for browser + server auto-detect and road seg.
# Run from repo root: ./scripts/download_ai_models.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST_DIR="${ROOT}/frontend/public/models"
SEG_DEST="${DEST_DIR}/yolov8n-seg-fp32.onnx"
CLS_DEST="${DEST_DIR}/yolov8n_cls_int8.onnx"

mkdir -p "$DEST_DIR"

need_python=false
if [[ ! -f "$SEG_DEST" ]] || [[ ! -f "$CLS_DEST" ]]; then
  need_python=true
fi

if $need_python && ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to export YOLO ONNX models." >&2
  exit 1
fi

export_models() {
  python3 - <<PY
from pathlib import Path
import shutil

root = Path("${ROOT}")
dest = root / "frontend/public/models"
dest.mkdir(parents=True, exist_ok=True)

try:
    from ultralytics import YOLO
except ImportError as exc:
    raise SystemExit(
        "ultralytics is required. Install with: pip install ultralytics onnx onnxruntime"
    ) from exc

seg_out = dest / "yolov8n-seg-fp32.onnx"
if not seg_out.exists():
    print("Exporting yolov8n-seg → ONNX (this may download weights on first run)...")
    seg = YOLO("yolov8n-seg.pt")
    exported = seg.export(format="onnx", imgsz=640, simplify=True)
    exported_path = Path(str(exported))
    if not exported_path.exists():
        exported_path = Path("yolov8n-seg.onnx")
    shutil.copy2(exported_path, seg_out)
    print(f"Saved {seg_out}")

cls_out = dest / "yolov8n_cls_int8.onnx"
if not cls_out.exists():
    print("Exporting yolov8n-cls → ONNX (this may download weights on first run)...")
    cls = YOLO("yolov8n-cls.pt")
    exported = cls.export(format="onnx", imgsz=224, simplify=True)
    exported_path = Path(str(exported))
    if not exported_path.exists():
        exported_path = Path("yolov8n-cls.onnx")
    shutil.copy2(exported_path, cls_out)
    print(f"Saved {cls_out}")

print("AI model export complete.")
PY
}

if $need_python; then
  (cd "$ROOT" && export_models)
fi

if [[ -f "$SEG_DEST" ]]; then
  echo "✓ Segmentation model: $SEG_DEST ($(du -h "$SEG_DEST" | awk '{print $1}'))"
else
  echo "✗ Missing segmentation model: $SEG_DEST" >&2
  exit 1
fi

if [[ -f "$CLS_DEST" ]]; then
  echo "✓ Classification model: $CLS_DEST ($(du -h "$CLS_DEST" | awk '{print $1}'))"
else
  echo "✗ Missing classification model: $CLS_DEST" >&2
  exit 1
fi

echo ""
echo "Road surface auto-segment needs a trained road model at ROAD_SEG_MODEL_PATH"
echo "(e.g. models/road_seg/best.pt). Object auto-detect uses the seg/cls ONNX above."
