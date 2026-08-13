#!/usr/bin/env python3
"""
Train YOLOv8-seg for road surface instance segmentation.

Usage:
    python scripts/train_road_seg.py --data road_dataset.yaml --model yolov8n-seg.pt --epochs 100 --imgsz 640

Requirements (training env only, not production):
    pip install ultralytics torch torchvision
"""
import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args():
    parser = argparse.ArgumentParser(description="Train YOLOv8-seg for road surface segmentation")
    parser.add_argument("--data", type=str, default="road_dataset.yaml", help="Dataset config YAML")
    parser.add_argument("--model", type=str, default="yolov8n-seg.pt", help="Base model (nano/small/medium)")
    parser.add_argument("--epochs", type=int, default=100, help="Number of training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Input image size")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--lr", type=float, default=0.01, help="Initial learning rate")
    parser.add_argument("--device", type=str, default="", help="Device (cuda:0, cpu)")
    parser.add_argument("--project", type=str, default="runs/segment", help="Project directory")
    parser.add_argument("--name", type=str, default="train", help="Experiment name")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--val", action="store_true", help="Run validation only")
    return parser.parse_args()


def main():
    args = parse_args()

    model = YOLO(args.model)

    if args.val:
        results = model.val(
            data=args.data,
            imgsz=args.imgsz,
            batch=args.batch,
            device=args.device,
            project=args.project,
            name=args.name,
        )
        print(results)
        return

    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        lr0=args.lr,
        device=args.device,
        project=args.project,
        name=args.name,
        resume=args.resume,
        patience=20,
        save=True,
        save_period=10,
        val=True,
        amp=True,
        fraction=1.0,
        profile=False,
        overlap_mask=True,
        mask_ratio=4,
        dropout=0.0,
        seed=42,
        deterministic=True,
        cos_lr=True,
        warmup_epochs=3,
        warmup_momentum=0.8,
        warmup_bias_lr=0.1,
        optimizer="AdamW",
        verbose=True,
    )

    print(f"Training completed. Best model saved to: {results.save_dir}/weights/best.pt")

    export_path = model.export(format="onnx", imgsz=args.imgsz, dynamic=True, simplify=True)
    print(f"ONNX model exported to: {export_path}")


if __name__ == "__main__":
    main()
