#!/usr/bin/env bash
# Download Depth-Anything-V2-Small (ViT-S) ONNX for monocular depth estimation.
# Run from repo root: ./scripts/download_depth_model.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${ROOT}/frontend/public/models/depth_anything_v2_vits.onnx"
SHA256_FILE="${DEST}.sha256"
REL_PATH="frontend/public/models/$(basename "$DEST")"

# HuggingFace mirror — update URL if upstream moves the artifact.
MODEL_URL="${DEPTH_MODEL_URL:-https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx}"

mkdir -p "$(dirname "$DEST")"

if [[ -f "$DEST" ]] && [[ -f "$SHA256_FILE" ]]; then
  expected="$(awk '{print $1}' "$SHA256_FILE")"
  actual="$(shasum -a 256 "$DEST" | awk '{print $1}')"
  if [[ "$expected" == "$actual" ]]; then
    echo "Model already present and checksum verified: $DEST"
    exit 0
  fi
  echo "Checksum mismatch — re-downloading"
fi

echo "Downloading Depth-Anything-V2-Small ONNX..."
curl -fsSL "$MODEL_URL" -o "$DEST"

actual="$(shasum -a 256 "$DEST" | awk '{print $1}')"
echo "$actual  $REL_PATH" > "$SHA256_FILE"
echo "Saved $DEST"
echo "SHA256: $actual"
echo "Verify with: shasum -a 256 -c ${SHA256_FILE}"
