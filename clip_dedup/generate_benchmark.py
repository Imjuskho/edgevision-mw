"""Generate benchmark datasets at 1k, 5k, and 10k image scales."""

import os
import random
import sys
import time

import numpy as np
from PIL import Image, ImageDraw


def _random_shape(draw, size):
    x0 = random.randint(0, size - 40)
    y0 = random.randint(0, size - 40)
    x1 = x0 + random.randint(20, 40)
    y1 = y0 + random.randint(20, 40)
    r, g, b = random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
    shape_type = random.choice(["rect", "ellipse", "triangle"])
    if shape_type == "rect":
        draw.rectangle([x0, y0, x1, y1], fill=(r, g, b))
    elif shape_type == "ellipse":
        draw.ellipse([x0, y0, x1, y1], fill=(r, g, b))
    else:
        draw.polygon([(x0, y1), ((x0 + x1) // 2, y0), (x1, y1)], fill=(r, g, b))


def _generate_image(size=224, seed=None):
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
    img = Image.new("RGB", (size, size), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    for _ in range(random.randint(3, 8)):
        _random_shape(draw, size)
    return img


def generate_dataset(out_dir: str, num_unique: int, num_near_groups: int, near_size: int,
                     num_exact_groups: int, exact_size: int):
    os.makedirs(out_dir, exist_ok=True)
    count = 0

    for i in range(num_unique):
        img = _generate_image(seed=i)
        img.save(os.path.join(out_dir, f"u_{i:05d}.jpg"))
        count += 1
        if count % 1000 == 0:
            print(f"  {count}...", flush=True)

    for g in range(num_near_groups):
        base_seed = 100000 + g
        base_img = _generate_image(seed=base_seed)
        base_img.save(os.path.join(out_dir, f"n_{g:04d}_a.jpg"))
        count += 1
        base_arr = np.array(base_img)
        for v in range(1, near_size):
            arr = base_arr.copy()
            noise = np.random.randint(-30, 30, arr.shape, dtype=np.int16)
            arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            Image.fromarray(arr).save(os.path.join(out_dir, f"n_{g:04d}_{chr(97+v)}.jpg"))
            count += 1
        if count % 1000 == 0:
            print(f"  {count}...", flush=True)

    for g in range(num_exact_groups):
        base_seed = 200000 + g
        img = _generate_image(seed=base_seed)
        for c in range(exact_size):
            img.save(os.path.join(out_dir, f"e_{g:04d}_{c:04d}.jpg"))
            count += 1
        if count % 1000 == 0:
            print(f"  {count}...", flush=True)

    print(f"  Done: {count} images", flush=True)
    return count


def main():
    sizes = [
        ("1k",  900, 10, 5, 5, 10),   # 900 + 50 + 50 = 1000
        ("5k",  4850, 10, 5, 10, 10),  # 4850 + 50 + 100 = 5000
        ("10k", 9850, 10, 5, 10, 10),  # 9850 + 50 + 100 = 10000
    ]

    for label, nu, ng, ns, eg, es in sizes:
        out = f"/tmp/clip_dedup_bench_{label}"
        print(f"\nGenerating {label} dataset ({nu + ng*ns + eg*es} images) → {out}")
        t0 = time.perf_counter()
        n = generate_dataset(out, nu, ng, ns, eg, es)
        elapsed = time.perf_counter() - t0
        print(f"  Generation time: {elapsed:.1f}s ({n/elapsed:.0f} img/s)")


if __name__ == "__main__":
    main()
