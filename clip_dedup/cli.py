from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from clip_dedup.dedup import run_dedup
from clip_dedup.embed import collect_images, compute_embeddings, load_model
from clip_dedup.report import generate_report

logger = logging.getLogger("clip_dedup")


def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname).1s %(message)s",
        stream=sys.stderr,
    )
    for noisy in ("httpx", "httpcore", "huggingface_hub", "urllib3", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main(argv: list[str] | None = None):
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", str(os.cpu_count() or 4))

    parser = argparse.ArgumentParser(
        description="CLIP-based image deduplication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m clip_dedup --input ./images --output ./cleaned\n"
            "  python -m clip_dedup --input ./images --threshold 0.98 --batch-size 128\n"
            "  python -m clip_dedup --input ./images --model ViT-L-14 --no-cache\n"
        ),
    )
    parser.add_argument("--input", required=True, help="Input image directory")
    parser.add_argument(
        "--output",
        default="./cleaned",
        help="Output directory for deduplicated images (default: ./cleaned)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.95,
        help="Cosine similarity threshold (default: 0.95)",
    )
    parser.add_argument(
        "--model",
        default="ViT-B-32",
        help="OpenCLIP model name (default: ViT-B-32)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Batch size for embedding (default: 64)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Thread count for image loading (default: 4)",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Directory for embedding cache (default: <output>/.clip_cache)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable embedding cache",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Path for HTML report (default: <output>/dedup_report.html)",
    )
    parser.add_argument(
        "--audit",
        default=None,
        help="Path for JSON audit log (default: <output>/dedup_audit.json)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bars",
    )
    parser.add_argument(
        "--ivf",
        action="store_true",
        help="Use IVF index for faster approximate search on large datasets",
    )

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    t_start = time.perf_counter()

    output_dir = args.output.rstrip("/")
    cache_dir = args.cache_dir or os.path.join(output_dir, ".clip_cache")
    report_path = args.report or os.path.join(output_dir, "dedup_report.html")
    audit_path = args.audit or os.path.join(output_dir, "dedup_audit.json")

    logger.info("Scanning images in %s", args.input)
    image_paths = collect_images(args.input)
    if not image_paths:
        logger.error("No images found in %s", args.input)
        sys.exit(1)
    logger.info("Found %d images", len(image_paths))

    logger.info("Loading model %s", args.model)
    model, preprocess, _tokenizer, device = load_model(args.model)

    compute_kwargs = dict(
        model=model,
        preprocess=preprocess,
        device=device,
        batch_size=args.batch_size,
        num_workers=args.workers,
        show_progress=not args.no_progress,
    )
    if not args.no_cache:
        compute_kwargs["cache_dir"] = cache_dir

    logger.info("Computing embeddings")
    embeddings, image_paths, valid_indices = compute_embeddings(
        image_paths, **compute_kwargs
    )
    logger.info(
        "Embeddings computed: shape=%s, valid=%d",
        embeddings.shape,
        len(valid_indices),
    )

    logger.info("Running dedup (threshold=%.3f)", args.threshold)
    audit_entries = run_dedup(
        embeddings,
        image_paths,
        valid_indices,
        threshold=args.threshold,
        output_dir=output_dir,
        audit_path=audit_path,
        use_ivf=args.ivf,
    )

    logger.info("Generating report")
    generate_report(
        audit_entries,
        total_images=len(image_paths),
        threshold=args.threshold,
        output_path=report_path,
    )

    elapsed = time.perf_counter() - t_start
    dup_count = sum(len(e["removed"]) for e in audit_entries)

    logger.info(
        "Done: %d images, %d duplicates removed (%d groups) in %.1fs | "
        "report=%s audit=%s output=%s",
        len(image_paths),
        dup_count,
        len(audit_entries),
        elapsed,
        report_path,
        audit_path,
        output_dir,
    )


if __name__ == "__main__":
    main()
