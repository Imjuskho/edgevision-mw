#!/usr/bin/env python3
"""
Export trained YOLOv8-seg model to ONNX for EdgeVision-MW deployment.

Produces two variants:
1. FP32 for browser (ONNX Runtime Web) — yolov8n-seg.onnx
2. FP16 for server (faster inference) — yolov8s-seg-fp16.onnx

Usage:
    python scripts/export_road_seg_onnx.py --weights runs/segment/train/weights/best.pt --output ./models/

Requirements:
    pip install ultralytics onnx onnxruntime
"""
import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args():
    parser = argparse.ArgumentParser(description="Export YOLOv8-seg to ONNX")
    parser.add_argument("--weights", type=str, required=True, help="Path to trained weights (.pt)")
    parser.add_argument("--output", type=str, default="./models/", help="Output directory")
    parser.add_argument("--imgsz", type=int, default=640, help="Input image size")
    return parser.parse_args()


def export_onnx(model: YOLO, output_path: str, imgsz: int, fp16: bool = False):
    """Export model to ONNX format."""
    model.export(
        format="onnx",
        imgsz=[imgsz, imgsz],
        dynamic=True,
        simplify=True,
        half=fp16,
    )

    suffix = "fp16" if fp16 else "fp32"
    src = Path(model.ckpt_path).parent / "best.onnx"
    dst = Path(output_path) / f"yolov8n-seg-{suffix}.onnx"
    if src.exists():
        import shutil
        shutil.copy(src, dst)
        print(f"Exported ONNX model to: {dst} ({src.stat().st_size / 1e6:.1f} MB)")
    else:
        print(f"Warning: ONNX file not found at {src}")


def main():
    args = parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(args.weights)

    # Export FP32 for browser (YOLOv8n-seg)
    export_onnx(model, str(output_dir), args.imgsz, fp16=False)

    print("Export complete!")


if __name__ == "__main__":
    main()
