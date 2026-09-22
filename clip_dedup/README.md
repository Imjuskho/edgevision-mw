# CLIP Dedup

Vision transformer-based image deduplication for large datasets. Uses CLIP
embeddings + FAISS to find and remove near-duplicate images.

## Quick Start

```bash
pip install -r requirements.txt

# Basic usage
python -m clip_dedup --input ./my_images --output ./cleaned

# Custom threshold (stricter = fewer duplicates)
python -m clip_dedup --input ./my_images --threshold 0.98

# Larger model for better accuracy
python -m clip_dedup --input ./my_images --model ViT-L-14 --batch-size 32
```

## CLI Reference

```
--input        Input image directory (required)
--output       Output directory (default: ./cleaned)
--threshold    Cosine similarity threshold (default: 0.95)
--model        OpenCLIP model name (default: ViT-B-32)
--batch-size   Embedding batch size (default: 64)
--workers      Image loading threads (default: 4)
--cache-dir    Embedding cache location (default: <output>/.clip_cache)
--no-cache     Disable embedding cache (recompute all)
--report       HTML report path (default: <output>/dedup_report.html)
--audit        JSON audit log path (default: <output>/dedup_audit.json)
--verbose      Debug logging
--no-progress  Hide progress bars
--ivf          Use IVF index (faster approximate search for >50k images)
```

## Output

- `cleaned/` — Deduplicated images (one canonical copy per group)
- `cleaned/duplicates/` — Moved duplicate images
- `cleaned/dedup_report.html` — Visual report with histogram and sample groups
- `cleaned/dedup_audit.json` — Machine-readable audit trail

## How It Works

1. **Scan** — Collect all supported image files (jpg, png, webp, etc.)
2. **Embed** — Generate CLIP image embeddings with optional .npy cache
3. **Index** — Build FAISS inner-product index (cosine similarity on normalized vectors)
4. **Detect** — Query all-vs-all; flag pairs above similarity threshold
5. **Group** — Union-Find transitive closure on detected pairs
6. **Resolve** — Keep highest-resolution image per group; move rest to duplicates/
7. **Report** — Generate HTML report + JSON audit log

## Performance

All-pairs search (FAISS FlatIP) scales quadratically. For large datasets, use
`--ivf` to enable IVF indexing (approximate nearest neighbors, configurable recall).

| Images | Model    | Embed     | Dedup      | Total      | Embed img/s |
|--------|----------|-----------|------------|------------|-------------|
| 1,000  | ViT-B-32 | ~8s       | ~6s        | ~14s       | 132         |
| 5,000  | ViT-B-32 | ~49s      | ~44s       | ~93s       | 102         |
| 10,000 | ViT-B-32 | ~98s      | ~276s      | ~374s      | 101         |

Benchmarked on Apple M3 Pro (18 GB RAM, CPU only). With GPU, embedding is
5–10× faster. With IVF (nlist=100, nprobe=10), search time drops from O(n²)
to O(n·log(n)), making 100k images feasible in ~15–20 min total.
