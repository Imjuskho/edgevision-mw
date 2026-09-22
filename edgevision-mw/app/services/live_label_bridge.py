"""Convert live WebSocket detections into studio ``human_labels`` boxes."""

from __future__ import annotations


def live_detections_to_studio_boxes(
    objects: list[dict],
    frame_width: int,
    frame_height: int,
) -> list[dict]:
    """Normalize live AI objects (pixel bbox + optional mask polygon) to studio box dicts."""
    if not objects:
        return []

    w = max(int(frame_width), 1)
    h = max(int(frame_height), 1)
    boxes: list[dict] = []

    for obj in objects:
        if not isinstance(obj, dict):
            continue

        label = obj.get("taxonomy_label") or obj.get("class_name") or obj.get("label") or "object"
        confidence = float(obj.get("confidence", 1.0))

        polygon: list[list[float]] | None = None
        mask = obj.get("mask")
        if (
            isinstance(mask, list)
            and len(mask) >= 3
            and mask
            and isinstance(mask[0], (list, tuple))
            and len(mask[0]) >= 2
        ):
            polygon = [[max(0.0, min(1.0, float(p[0]))), max(0.0, min(1.0, float(p[1])))] for p in mask[:32]]

        bbox = obj.get("bbox")
        if polygon:
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            nx = max(0.0, min(xs))
            ny = max(0.0, min(ys))
            nw = max(0.001, min(1.0, max(xs) - nx))
            nh = max(0.001, min(1.0, max(ys) - ny))
        elif isinstance(bbox, list) and len(bbox) >= 4:
            x, y, third, fourth = (float(v) for v in bbox[:4])
            if third > x and (third > 1.0 or fourth > 1.0 or x > 1.0 or y > 1.0):
                nx = x / w
                ny = y / h
                nw = (third - x) / w
                nh = (fourth - y) / h
            elif third > 1.0 or fourth > 1.0 or x > 1.0 or y > 1.0:
                nx = x / w
                ny = y / h
                nw = third / w
                nh = fourth / h
            else:
                nx, ny, nw, nh = x, y, third, fourth
            nx = max(0.0, min(1.0, nx))
            ny = max(0.0, min(1.0, ny))
            nw = max(0.001, min(1.0, nw))
            nh = max(0.001, min(1.0, nh))
        else:
            continue

        entry: dict = {
            "x": round(nx, 6),
            "y": round(ny, 6),
            "width": round(nw, 6),
            "height": round(nh, 6),
            "label": str(label),
            "confidence": round(confidence, 4),
            "category": str(label).split("_")[0],
            "engine": "live_ai",
        }
        if polygon:
            entry["polygon"] = polygon
        if obj.get("bbox_3d"):
            entry["bbox_3d"] = obj["bbox_3d"]
        if obj.get("track_id") is not None:
            entry["track_id"] = obj["track_id"]
        boxes.append(entry)

    return boxes
