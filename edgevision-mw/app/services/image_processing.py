from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("edgevision.image_processing")

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "TIFF", "BMP"}
# Normalize these to PNG
NORMALIZE_TO_PNG = {"WEBP", "TIFF", "BMP"}
MAX_DIMENSION = 16384


class ImageValidationError(ValueError):
    pass


@dataclass
class ImageMeta:
    width: int
    height: int
    format: str
    mode: str
    has_alpha: bool


def validate_image(file_bytes: bytes) -> ImageMeta:
    try:
        img = Image.open(BytesIO(file_bytes))
        img.verify()
        # Re-open after verify (verify closes the file)
        img = Image.open(BytesIO(file_bytes))
        width, height = img.size
        fmt = img.format.upper() if img.format else "UNKNOWN"

        if fmt not in ALLOWED_FORMATS and fmt != "JPEG":
            raise ImageValidationError(f"Unsupported image format: {fmt}")

        if width == 0 or height == 0:
            raise ImageValidationError("Image has zero dimensions")

        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            raise ImageValidationError(
                f"Image dimensions {width}x{height} exceed max {MAX_DIMENSION}x{MAX_DIMENSION}"
            )

        has_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info

        return ImageMeta(
            width=width,
            height=height,
            format=fmt,
            mode=img.mode,
            has_alpha=has_alpha,
        )
    except ImageValidationError:
        raise
    except Exception as exc:
        raise ImageValidationError(f"Image is corrupt or invalid: {exc}") from exc


def normalize_image(
    file_bytes: bytes,
    target_format: str = "JPEG",
    strip_exif: bool | None = None,
) -> tuple[bytes, str]:
    if strip_exif is None:
        strip_exif = getattr(settings, "STRIP_EXIF_ON_UPLOAD", True)

    img = Image.open(BytesIO(file_bytes))
    fmt = img.format.upper() if img.format else "UNKNOWN"

    output_format = target_format
    if fmt in NORMALIZE_TO_PNG:
        output_format = "PNG"
        if fmt == "WEBP":
            img = img.convert("RGBA") if img.mode != "RGBA" else img
        if fmt == "TIFF":
            img = img.convert("RGB") if img.mode == "CMYK" else img
    elif fmt == "JPEG":
        output_format = "JPEG"

    if output_format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode == "RGBA":
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img)
        img = background

    if output_format == "JPEG" and img.mode != "RGB":
        img = img.convert("RGB")

    if strip_exif:
        exif_data = img.info.get("exif")
        if exif_data:
            logger.debug("stripping_exif", format=fmt)
        img.info.pop("exif", None)

    buf = BytesIO()
    save_kwargs = {}
    if output_format == "JPEG":
        save_kwargs["quality"] = 92
    elif output_format == "PNG":
        save_kwargs["compress_level"] = 6

    img.save(buf, format=output_format, **save_kwargs)
    return buf.getvalue(), output_format


def generate_thumbnail(
    file_bytes: bytes,
    size: tuple[int, int] = (256, 256),
) -> bytes:
    img = Image.open(BytesIO(file_bytes))
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    img.thumbnail(size, Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def extract_exif(file_bytes: bytes) -> dict | None:
    try:
        img = Image.open(BytesIO(file_bytes))
        exif_data = img.getexif()
        if not exif_data:
            return None

        result = {}
        gps_ifd = exif_data.get_ifd(0x8825)
        if gps_ifd:
            gps_info = {}
            for tag_id, value in gps_ifd.items():
                tag_name = _GPS_TAGS.get(tag_id, str(tag_id))
                gps_info[tag_name] = value
            if gps_info:
                result["gps"] = gps_info
                lat, lon = _extract_gps_coords(exif_data)
                if lat is not None and lon is not None:
                    result["gps_lat"] = lat
                    result["gps_lon"] = lon

        for tag_id in (0x010F, 0x0110, 0x010E, 0x0112, 0x0132, 0x829A, 0x829D, 0x8827, 0xA217, 0xA420):
            if tag_id in exif_data:
                tag_name = _EXIF_TAGS.get(tag_id, str(tag_id))
                val = exif_data[tag_id]
                if isinstance(val, bytes):
                    try:
                        val = val.decode("utf-8", errors="replace")
                    except Exception:
                        val = str(val)
                result[tag_name] = val

        return result if result else None
    except Exception as exc:
        logger.debug("exif_extraction_failed", error=str(exc))
        return None


def _to_degrees(value: tuple[int, int, int]) -> float:
    d, m, s = value
    return float(d) + float(m) / 60.0 + float(s) / 3600.0


def _extract_gps_coords(exif_data) -> tuple[float | None, float | None]:
    try:
        gps_ifd = exif_data.get_ifd(0x8825)
        if gps_ifd is None:
            return None, None

        lat_data = gps_ifd.get(2)
        lat_ref = gps_ifd.get(1)
        lon_data = gps_ifd.get(4)
        lon_ref = gps_ifd.get(3)

        if lat_data is None or lon_data is None:
            return None, None

        lat = _to_degrees(lat_data)
        lon = _to_degrees(lon_data)

        if lat_ref and lat_ref == b"S":
            lat = -lat
        if lon_ref and lon_ref == b"W":
            lon = -lon

        return lat, lon
    except Exception:
        return None, None


_EXIF_TAGS = {
    0x010F: "make",
    0x0110: "model",
    0x010E: "image_description",
    0x0112: "orientation",
    0x0132: "datetime",
    0x829A: "exposure_time",
    0x829D: "f_number",
    0x8827: "iso",
    0xA217: "sensing_method",
    0xA420: "image_unique_id",
}

_GPS_TAGS = {
    0: "gps_version",
    1: "gps_lat_ref",
    2: "gps_lat",
    3: "gps_lon_ref",
    4: "gps_lon",
    5: "gps_alt_ref",
    6: "gps_altitude",
    7: "gps_time_stamp",
    8: "gps_satellites",
    9: "gps_status",
    10: "gps_measure_mode",
    11: "gps_dop",
    12: "gps_speed_ref",
    13: "gps_speed",
    14: "gps_track_ref",
    15: "gps_track",
    16: "gps_img_dir_ref",
    17: "gps_img_dir",
    18: "gps_map_datum",
    19: "gps_dest_lat_ref",
    20: "gps_dest_lat",
    21: "gps_dest_lon_ref",
    22: "gps_dest_lon",
    23: "gps_dest_bearing_ref",
    24: "gps_dest_bearing",
    25: "gps_dest_distance_ref",
    26: "gps_dest_distance",
    27: "gps_processing_method",
    28: "gps_area_information",
    29: "gps_date_stamp",
    30: "gps_differential",
}
