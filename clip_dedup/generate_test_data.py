"""Generate synthetic test images for CLIP Dedup validation.

Produces 100 images with controlled duplicates:
- 30 completely unique images (distinct colors/svg-like shapes)
- 10 sets of 5 near-duplicates each (same shape, small color/transform variation)
- 2 sets of 10 exact duplicates each
"""

import os
import random

import numpy as np
from PIL import Image, ImageDraw


def _random_shape(draw, size):
    x0 = random.randint(0, size - 40)
    y0 = random.randint(0, size - 40)
    x1 = x0 + random.randint(20, 40)
    y1 = y0 + random.randint(20, 40)
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)
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


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "test_data")
    os.makedirs(out_dir, exist_ok=True)

    idx = 0

    for i in range(30):
        img = _generate_image(seed=i)
        img.save(os.path.join(out_dir, f"unique_{i:04d}.jpg"))

    for group in range(10):
        base_seed = 100 + group
        base_img = _generate_image(seed=base_seed)
        base_img.save(os.path.join(out_dir, f"near_dup_{group:04d}_a.jpg"))
        base_arr = np.array(base_img)
        for variant in range(1, 5):
            arr = base_arr.copy()
            noise = np.random.randint(-30, 30, arr.shape, dtype=np.int16)
            arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            Image.fromarray(arr).save(
                os.path.join(out_dir, f"near_dup_{group:04d}_{chr(98 + variant)}.jpg")
            )

    for group in range(2):
        base_seed = 200 + group
        img = _generate_image(seed=base_seed)
        for copy_idx in range(10):
            img.save(os.path.join(out_dir, f"exact_dup_{group:04d}_{copy_idx:04d}.jpg"))

    all_files = [f for f in os.listdir(out_dir) if f.endswith(".jpg")]
    print(f"Generated {len(all_files)} test images in {out_dir}/")


if __name__ == "__main__":
    main()
