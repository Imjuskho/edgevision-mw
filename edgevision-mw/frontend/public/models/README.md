# ONNX Model Artifacts

Large model files are not committed to git. Download them locally:

## Depth-Anything-V2-Small (monocular depth)

```bash
./scripts/download_depth_model.sh
```

Expected artifact: `depth_anything_v2_vits.onnx` (+ `.sha256` sidecar).

| Property | Value |
|----------|-------|
| File | `depth_anything_v2_vits.onnx` |
| Size | ~94.5 MB (99,060,839 bytes) |
| SHA256 | `afb6a5c28f3b6bf1618c6e43f02073ef9dfdc70e937502d51603e57b0a1df10c` |

Verify from repo root:

```bash
shasum -a 256 -c frontend/public/models/depth_anything_v2_vits.onnx.sha256
```

Source: [onnx-community/depth-anything-v2-small](https://huggingface.co/onnx-community/depth-anything-v2-small) (`onnx/model.onnx`). Override URL with `DEPTH_MODEL_URL` if HuggingFace is unreachable.

When the ONNX file is absent, the backend falls back to a vertical-gradient heuristic and sets `depth_available: false` in live annotation responses.

## Other models

Run from repo root to export YOLO ONNX weights for auto-detect (browser + server):

```bash
./scripts/download_ai_models.sh
```

Expected artifacts:

| File | Purpose |
|------|---------|
| `yolov8n-seg-fp32.onnx` | Object detection / instance masks (COCO) |
| `yolov8n_cls_int8.onnx` | Classification fallback for pre-label grid |

Road **surface** auto-segment needs a separately trained model (7 road classes). Set `ROAD_SEG_MODEL_PATH` to your trained `.pt` or `.onnx` export (e.g. `models/road_seg/best.pt`).

See project root `AGENTS.md` for MobileSAM, YOLO, and CLIP artifact locations.
