"""Low-light and weather robustness handling.

Provides:
- Image quality assessment (brightness, contrast, noise)
- Low-light detection and model variant selection
- Weather condition tagging
- IR camera support hooks
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import numpy as np

@dataclass
class ImageQualityMetrics:
    """Image quality assessment metrics."""
    brightness: float  # 0-255 mean
    contrast: float  # std deviation
    noise_estimate: float  # high-frequency energy
    is_low_light: bool
    is_high_noise: bool
    recommended_model_variant: str  # "standard", "low_light", "ir_enhanced"
    quality_score: float  # 0-1
    lighting_condition: str  # "bright", "normal", "dim", "dark"

@dataclass
class WeatherTag:
    """Weather condition tag for a frame."""
    condition: str  # "clear", "cloudy", "rain", "fog", "night", "glare"
    confidence: float
    solar_input_watts: float | None = None
    visibility_estimate: str | None = None  # "good", "reduced", "poor"

def assess_image_quality(image_bytes: bytes) -> ImageQualityMetrics:
    """Assess image quality for model variant selection."""
    try:
        import cv2
        import numpy as np
        
        arr = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if arr is None:
            return ImageQualityMetrics(
                brightness=0, contrast=0, noise_estimate=0,
                is_low_light=True, is_high_noise=False,
                recommended_model_variant="low_light",
                quality_score=0.0,
                lighting_condition="dark",
            )
        
        brightness = float(np.mean(arr))
        contrast = float(np.std(arr))
        
        # Noise estimate via high-pass filter
        kernel = np.array([[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]], dtype=np.float64)
        high_freq = cv2.filter2D(arr.astype(np.float64), -1, kernel)
        noise = float(np.std(high_freq))
        
        is_low = brightness < 60
        is_noisy = noise > 50
        
        if is_low and is_noisy:
            variant = "low_light"
        elif is_low:
            variant = "low_light"
        else:
            variant = "standard"
        
        if brightness < 30:
            lighting = "dark"
        elif brightness < 80:
            lighting = "dim"
        elif brightness < 180:
            lighting = "normal"
        else:
            lighting = "bright"
        
        quality = 1.0
        quality *= min(1.0, brightness / 100.0)
        quality *= min(1.0, contrast / 60.0)
        quality *= max(0.3, 1.0 - noise / 100.0)
        
        return ImageQualityMetrics(
            brightness=round(brightness, 2),
            contrast=round(contrast, 2),
            noise_estimate=round(noise, 2),
            is_low_light=is_low,
            is_high_noise=is_noisy,
            recommended_model_variant=variant,
            quality_score=round(max(0.0, min(1.0, quality)), 3),
            lighting_condition=lighting,
        )
    except Exception:
        return ImageQualityMetrics(
            brightness=0, contrast=0, noise_estimate=0,
            is_low_light=True, is_high_noise=False,
            recommended_model_variant="low_light",
            quality_score=0.0,
            lighting_condition="dark",
        )

def tag_weather_condition(
    solar_input_watts: float = 0.0,
    image_quality: ImageQualityMetrics | None = None,
    lte_rssi_dbm: float = -70.0,
) -> WeatherTag:
    """Tag weather/lighting condition from available telemetry."""
    if solar_input_watts > 50:
        condition = "clear"
        confidence = 0.9
        visibility = "good"
    elif solar_input_watts > 20:
        condition = "cloudy"
        confidence = 0.7
        visibility = "good"
    elif solar_input_watts > 5:
        condition = "overcast"
        confidence = 0.6
        visibility = "reduced"
    else:
        condition = "night"
        confidence = 0.8
        visibility = "reduced" if image_quality and not image_quality.is_low_light else "poor"
    
    if image_quality and image_quality.is_high_noise:
        condition = "rain"
        confidence = 0.5
        visibility = "poor"
    
    return WeatherTag(
        condition=condition,
        confidence=confidence,
        solar_input_watts=solar_input_watts,
        visibility_estimate=visibility,
    )

def enhance_low_light(image_bytes: bytes, strength: float = 1.5) -> bytes:
    """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) for low-light."""
    try:
        import cv2
        import numpy as np
        
        arr = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return image_bytes
        
        lab = cv2.cvtColor(arr, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]
        
        clahe = cv2.createCLAHE(clipLimit=2.0 * strength, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(l_channel)
        
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        _, encoded = cv2.imencode(".jpg", enhanced, [cv2.IMWRITE_JPEG_QUALITY, 95])
        return encoded.tobytes()
    except Exception:
        return image_bytes
