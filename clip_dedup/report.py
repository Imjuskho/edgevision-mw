from __future__ import annotations

import base64
import io
import logging
import os
from string import Template

from PIL import Image

logger = logging.getLogger("clip_dedup.report")

_HTML_TEMPLATE = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CLIP Dedup Report</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;max-width:960px;margin:40px auto;padding:0 20px;color:#333;background:#fafafa}
h1{color:#1a1a1a;border-bottom:2px solid #e0e0e0;padding-bottom:10px}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;margin:24px 0}
.card{background:#fff;border-radius:8px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card .value{font-size:2em;font-weight:700;color:#2563eb}
.card .label{font-size:.85em;color:#666;margin-top:4px}
.histogram{margin:24px 0;background:#fff;border-radius:8px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.bar-container{display:flex;align-items:center;gap:8px;margin:4px 0}
.bar-label{width:60px;text-align:right;font-size:.8em;color:#666}
.bar{height:20px;background:#2563eb;border-radius:4px;transition:width .3s}
.groups h2{margin-top:32px}
.group-card{background:#fff;border-radius:8px;padding:16px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.group-card .canonical{font-weight:600;color:#16a34a}
.group-card .removed{color:#dc2626}
.thumb-grid{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.thumb-grid img{width:100px;height:100px;object-fit:cover;border-radius:4px;border:1px solid #e0e0e0}
.thumb-grid .caption{text-align:center;font-size:.7em;color:#666;max-width:100px;word-break:break-all}
.thumb-item{text-align:center}
</style>
</head>
<body>
<h1>CLIP Dedup Report</h1>
<div class="summary">
<div class="card"><div class="value">$total_images</div><div class="label">Total Images</div></div>
<div class="card"><div class="value">$duplicates_removed</div><div class="label">Duplicates Removed</div></div>
<div class="card"><div class="value">$num_groups</div><div class="label">Duplicate Groups</div></div>
<div class="card"><div class="value">$threshold</div><div class="label">Similarity Threshold</div></div>
</div>
$histogram_section
<div class="groups">
<h2>Duplicate Groups ($num_groups)</h2>
$group_cards
</div>
</body>
</html>""")


def _similarity_histogram(audit_entries: list[dict]) -> str:
    all_sims = []
    for entry in audit_entries:
        all_sims.extend(entry.get("similarities", []))
    if not all_sims:
        return ""

    buckets = [0] * 10
    for sim in all_sims:
        b = min(int(sim * 10), 9)
        buckets[b] += 1

    lines = ['<div class="histogram"><h3>Similarity Distribution</h3>']
    for i in range(10):
        lo = i / 10.0
        hi = (i + 1) / 10.0
        pct = max(1, int(buckets[i] / max(1, max(buckets)) * 300))
        lines.append(
            f'<div class="bar-container">'
            f'<span class="bar-label">{lo:.1f}-{hi:.1f}</span>'
            f'<div class="bar" style="width:{pct}px"></div>'
            f"<span> {buckets[i]}</span>"
            f"</div>"
        )
    lines.append("</div>")
    return "\n".join(lines)


def _image_thumbnail(path: str, size: tuple[int, int] = (100, 100)) -> str:
    try:
        with Image.open(path) as img:
            img.thumbnail(size)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60)
            b64 = base64.b64encode(buf.getvalue()).decode()
            return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return ""


def _group_card(entry: dict) -> str:
    kept_path = entry["kept"]
    removed_paths = entry["removed"]

    kept_thumb = _image_thumbnail(kept_path)
    kept_basename = os.path.basename(kept_path)

    removed_thumbs = ""
    for rp in removed_paths:
        rt = _image_thumbnail(rp)
        rn = os.path.basename(rp)
        removed_thumbs += (
            f'<div class="thumb-item">'
            f'<img src="{rt}" alt="{rn}">'
            f'<div class="caption">{rn}</div>'
            f"</div>"
        )

    return (
        f'<div class="group-card">'
        f"<details open>"
        f'<summary>Group ({entry["group_size"]} images)</summary>'
        f'<p class="canonical">Kept: {kept_basename}</p>'
        f'<div class="thumb-grid">'
        f'<div class="thumb-item">'
        f'<img src="{kept_thumb}" alt="{kept_basename}" style="border:3px solid #16a34a">'
        f'<div class="caption">{kept_basename}</div>'
        f"</div>"
        f"{removed_thumbs}"
        f"</div>"
        f"</details>"
        f"</div>"
    )


def generate_report(
    audit_entries: list[dict],
    total_images: int,
    threshold: float,
    output_path: str,
):
    total_removed = sum(len(e["removed"]) for e in audit_entries)
    num_groups = len(audit_entries)

    histogram_section = _similarity_histogram(audit_entries)
    group_cards = "\n".join(_group_card(e) for e in audit_entries)

    html = _HTML_TEMPLATE.substitute(
        total_images=total_images,
        duplicates_removed=total_removed,
        num_groups=num_groups,
        threshold=threshold,
        histogram_section=histogram_section,
        group_cards=group_cards,
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)
    logger.info("Report generated: %s", output_path)
