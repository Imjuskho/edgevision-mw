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


def export_onnx(model: YOLO, output_path: str, imgsz: int, fp16: bool = False, dest_name: str = "best.onnx"):
    """Export model to ONNX format."""
    export_result = model.export(
        format="onnx",
        imgsz=[imgsz, imgsz],
        dynamic=True,
        simplify=True,
        half=fp16,
    )

    suffix = "fp16" if fp16 else "fp32"
    src = Path(export_result) if export_result else Path(model.ckpt_path).parent / "best.onnx"
    if not src.exists():
        src = Path(model.ckpt_path).with_suffix(".onnx")
    dst = Path(output_path) / dest_name
    if src.exists():
        import shutil
        if src.resolve() != dst.resolve():
            shutil.copy(src, dst)
        print(f"Exported ONNX model to: {dst} ({dst.stat().st_size / 1e6:.1f} MB)")
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
