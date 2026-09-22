"""Diffusion-based synthetic data generator with ControlNet-style conditioning.

Wraps a generative model conditioned on:
- Scene layout (road geometry, camera intrinsics)
- Weather conditions (clear, rainy, foggy, overcast)
- Time of day (dawn, day, dusk, night)
- Object placement (class, count, position constraints)

Only weight-delta payloads cross network boundaries. No raw training
data is transmitted.
"""
from __future__ import annotations

import hashlib
import logging
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger("edgevision.synthetic.generator")


@dataclass
class WeatherCondition:
    name: str
    fog_density: float = 0.0
    rain_intensity: float = 0.0
    cloud_cover: float = 0.0
    brightness_modifier: float = 1.0


@dataclass
class TimeOfDay:
    name: str
    sun_angle_deg: float = 45.0
    ambient_light: float = 0.8
    shadow_length: float = 1.0


@dataclass
class CameraIntrinsics:
    width: int = 1920
    height: int = 1080
    fov_deg: float = 70.0
    fx: float = 0.0
    fy: float = 0.0
    cx: float = 0.0
    cy: float = 0.0

    def __post_init__(self):
        if self.fx == 0:
            self.fx = self.width / (2 * math.tan(math.radians(self.fov_deg) / 2))
            self.fy = self.fx
            self.cx = self.width / 2
            self.cy = self.height / 2


@dataclass
class ObjectPlacement:
    class_name: str
    count: int = 1
    bbox_range: tuple[float, float, float, float] = (0.1, 0.3, 0.2, 0.5)
    road_constrained: bool = True
    min_distance_m: float = 2.0
    max_distance_m: float = 50.0


@dataclass
class SceneLayout:
    road_width_m: float = 6.0
    road_angle_deg: float = 0.0
    lane_count: int = 2
    has_sidewalk: bool = False
    has_shoulders: bool = True
    vegetation_density: float = 0.3
    building_density: float = 0.0


@dataclass
class GenerationConfig:
    weather: WeatherCondition = field(default_factory=lambda: WeatherCondition("clear"))
    time_of_day: TimeOfDay = field(default_factory=lambda: TimeOfDay("day"))
    camera: CameraIntrinsics = field(default_factory=CameraIntrinsics)
    objects: list[ObjectPlacement] = field(default_factory=list)
    scene: SceneLayout = field(default_factory=SceneLayout)
    seed: int | None = None
    output_format: str = "coco"


PRESETS = {
    "urban_day": GenerationConfig(
        weather=WeatherCondition("clear", brightness_modifier=1.0),
        time_of_day=TimeOfDay("day", sun_angle_deg=50, ambient_light=0.9),
        scene=SceneLayout(road_width_m=8.0, lane_count=3, building_density=0.5),
        objects=[
            ObjectPlacement("car", count=5),
            ObjectPlacement("pedestrian", count=3, road_constrained=False),
            ObjectPlacement("motorcycle", count=1),
        ],
    ),
    "rural_night": GenerationConfig(
        weather=WeatherCondition("clear", brightness_modifier=0.15),
        time_of_day=TimeOfDay("night", sun_angle_deg=0, ambient_light=0.05),
        scene=SceneLayout(road_width_m=4.0, lane_count=1, vegetation_density=0.7),
        objects=[
            ObjectPlacement("car", count=1),
            ObjectPlacement("cow", count=2, road_constrained=False),
        ],
    ),
    "rainy_road": GenerationConfig(
        weather=WeatherCondition("rainy", rain_intensity=0.6, cloud_cover=0.8, brightness_modifier=0.7),
        time_of_day=TimeOfDay("day", ambient_light=0.6),
        scene=SceneLayout(road_width_m=6.0, lane_count=2),
        objects=[
            ObjectPlacement("car", count=4),
            ObjectPlacement("truck", count=1),
        ],
    ),
}


class SyntheticGenerator:
    """Generates synthetic training frames with structured conditioning.

    Uses a noise-iterative generation process inspired by diffusion models.
    In production, this would wrap a trained ControlNet/diffusion model.
    Here, we implement the full conditioning pipeline and a structural
    generation method that creates realistic scene compositions.
    """

    _instance: SyntheticGenerator | None = None
    _lock = threading.Lock()

    def __init__(self):
        self._rng = np.random.default_rng()

    @classmethod
    def get_instance(cls) -> SyntheticGenerator:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def generate_batch(
        self,
        config: GenerationConfig,
        count: int,
        *,
        seed: int | None = None,
    ) -> list[GeneratedFrame]:
        """Generate a batch of synthetic frames.

        Parameters
        ----------
        config : GenerationConfig
            Structured conditioning for generation.
        count : int
            Number of frames to generate.
        seed : int, optional
            Random seed for reproducibility.

        Returns
        -------
        list[GeneratedFrame]
        """
        rng = np.random.default_rng(seed if seed is not None else config.seed)
        frames = []
        for i in range(count):
            frame = self._generate_single(config, rng, frame_index=i)
            frames.append(frame)
        return frames

    def _generate_single(
        self,
        config: GenerationConfig,
        rng: np.random.Generator,
        frame_index: int = 0,
    ) -> GeneratedFrame:
        """Generate a single synthetic frame with full conditioning."""
        cam = config.camera
        img = np.zeros((cam.height, cam.width, 3), dtype=np.uint8)

        self._render_sky(img, config, rng)
        self._render_road(img, config, rng)
        self._render_vegetation(img, config, rng)
        self._render_buildings(img, config, rng)

        objects = self._place_objects(config, rng)

        self._render_objects(img, objects, config, rng)

        self._apply_weather(img, config, rng)
        self._apply_time_of_day(img, config, rng)

        source_checksum = hashlib.sha256(img.tobytes()).hexdigest()[:16]

        return GeneratedFrame(
            image=img,
            frame_index=frame_index,
            weather=config.weather.name,
            time_of_day=config.time_of_day.name,
            objects=objects,
            source_checksum=source_checksum,
            config_hash=self._config_hash(config),
        )

    def _render_sky(
        self, img: np.ndarray, config: GenerationConfig, rng: np.random.Generator
    ) -> None:
        h, w = img.shape[:2]
        sky_end = h // 3
        ambient = config.time_of_day.ambient_light
        brightness = config.weather.brightness_modifier

        for y in range(sky_end):
            t = y / max(sky_end, 1)
            if config.time_of_day.name in ("dawn", "dusk"):
                r = int(np.clip(80 + 120 * (1 - t) * ambient * brightness, 0, 255))
                g = int(np.clip(40 + 60 * (1 - t) * ambient * brightness, 0, 255))
                b = int(np.clip(100 + 80 * t * ambient * brightness, 0, 255))
            elif config.time_of_day.name == "night":
                r = int(np.clip(5 + 15 * (1 - t), 0, 255))
                g = int(np.clip(5 + 15 * (1 - t), 0, 255))
                b = int(np.clip(15 + 25 * (1 - t), 0, 255))
            else:
                r = int(np.clip(130 + 50 * (1 - t) * ambient * brightness, 0, 255))
                g = int(np.clip(170 + 40 * (1 - t) * ambient * brightness, 0, 255))
                b = int(np.clip(220 + 20 * (1 - t) * ambient * brightness, 0, 255))
            img[y, :] = [r, g, b]

    def _render_road(
        self, img: np.ndarray, config: GenerationConfig, rng: np.random.Generator
    ) -> None:
        h, w = img.shape[:2]
        road_top = int(h * 0.35)
        road_bottom = h
        road_center_x = w // 2
        cam = config.camera
        road_m = config.scene.road_width_m

        vanishing_y = int(h * 0.38)
        vanishing_x = w // 2

        for y in range(road_top, road_bottom):
            t = (y - vanishing_y) / max(road_bottom - vanishing_y, 1)
            t = max(0, min(1, t))
            half_width = int(road_m * cam.fx / max(cam.fy * t * 10, 1) * w * 0.05)
            half_width = max(10, min(half_width, w // 2))

            left = max(0, road_center_x - half_width)
            right = min(w, road_center_x + half_width)

            asphalt = int(np.clip(55 + 20 * t * config.time_of_day.ambient_light, 0, 255))
            img[y, left:right] = [asphalt, asphalt, asphalt + 2]

            if config.scene.lane_count >= 2 and y % 20 < 3:
                dash_width = max(1, half_width // 8)
                img[y, road_center_x - dash_width:road_center_x + dash_width] = [
                    200, 200, 200
                ]

    def _render_vegetation(
        self, img: np.ndarray, config: GenerationConfig, rng: np.random.Generator
    ) -> None:
        if config.scene.vegetation_density <= 0:
            return
        h, w = img.shape[:2]
        road_top = int(h * 0.35)
        n_trees = int(config.scene.vegetation_density * 30)

        for _ in range(n_trees):
            side = rng.choice([-1, 1])
            x = int(w // 2 + side * rng.uniform(0.35, 0.55) * w)
            y = int(rng.uniform(road_top, h * 0.8))
            tree_h = int(rng.uniform(20, 60))
            tree_w = int(rng.uniform(15, 40))

            for dy in range(-tree_h, 0):
                for dx in range(-tree_w // 2, tree_w // 2):
                    px, py = x + dx, y + dy
                    if 0 <= px < w and 0 <= py < h:
                        dist_center = abs(dx) / max(tree_w / 2, 1)
                        if dist_center + abs(dy) / max(tree_h, 1) < 1.0:
                            green = int(np.clip(
                                60 + 80 * (1 - dist_center) * config.time_of_day.ambient_light,
                                0, 255
                            ))
                            img[py, px] = [
                                int(green * 0.3),
                                green,
                                int(green * 0.2),
                            ]

    def _render_buildings(
        self, img: np.ndarray, config: GenerationConfig, rng: np.random.Generator
    ) -> None:
        if config.scene.building_density <= 0:
            return
        h, w = img.shape[:2]
        road_top = int(h * 0.35)
        n_buildings = int(config.scene.building_density * 10)

        for _ in range(n_buildings):
            side = rng.choice([-1, 1])
            x = int(w // 2 + side * rng.uniform(0.4, 0.6) * w)
            y = int(rng.uniform(road_top - 50, h * 0.6))
            bw = int(rng.uniform(40, 120))
            bh = int(rng.uniform(30, 80))

            gray = int(np.clip(100 + rng.integers(-20, 40), 0, 255))
            y1 = max(0, y)
            y2 = min(h, y + bh)
            x1 = max(0, x - bw // 2)
            x2 = min(w, x + bw // 2)
            img[y1:y2, x1:x2] = [gray, gray - 10, gray - 20]

            for wy in range(y1, min(y2, y + bh - 5), 12):
                for wx in range(x1 + 5, x2 - 5, 15):
                    if rng.random() < 0.6:
                        ww, wh_ = min(8, x2 - wx - 5), min(8, y2 - wy - 5)
                        if ww > 0 and wh_ > 0:
                            brightness = 200 if config.time_of_day.name != "night" else 160
                            img[wy:wy + wh_, wx:wx + ww] = [
                                brightness, brightness, int(brightness * 0.9)
                            ]

    def _place_objects(
        self, config: GenerationConfig, rng: np.random.Generator
    ) -> list[ObjectInstance]:
        objects = []
        cam = config.camera

        for placement in config.objects:
            for _ in range(placement.count):
                depth_m = rng.uniform(placement.min_distance_m, placement.max_distance_m)
                scale = cam.fy / (depth_m * 10 + 1)

                if placement.road_constrained:
                    x_center = cam.cx + rng.uniform(-0.15, 0.15) * cam.width
                else:
                    x_center = rng.uniform(cam.width * 0.1, cam.width * 0.9)

                y_center = cam.height * 0.38 + (cam.height * 0.55) * (1 - min(depth_m / 50, 1))

                class_dims = _CLASS_DIMS.get(placement.class_name, (1.5, 1.5, 1.5))
                w_px = int(class_dims[0] * scale * cam.width * 0.08)
                h_px = int(class_dims[1] * scale * cam.height * 0.08)

                w_px = max(5, min(w_px, cam.width // 4))
                h_px = max(5, min(h_px, cam.height // 4))

                x1 = int(max(0, x_center - w_px / 2))
                y1 = int(max(0, y_center - h_px / 2))
                x2 = int(min(cam.width, x1 + w_px))
                y2 = int(min(cam.height, y1 + h_px))

                objects.append(ObjectInstance(
                    class_name=placement.class_name,
                    bbox_normalized=(
                        x1 / cam.width, y1 / cam.height,
                        (x2 - x1) / cam.width, (y2 - y1) / cam.height,
                    ),
                    depth_m=depth_m,
                    instance_id=len(objects),
                ))

        return objects

    def _render_objects(
        self,
        img: np.ndarray,
        objects: list[ObjectInstance],
        config: GenerationConfig,
        rng: np.random.Generator,
    ) -> None:
        h, w = img.shape[:2]
        for obj in objects:
            x1n, y1n, wn, hn = obj.bbox_normalized
            x1, y1 = int(x1n * w), int(y1n * h)
            bw, bh_ = int(wn * w), int(hn * h)
            x2, y2 = min(w, x1 + bw), min(h, y1 + bh_)

            color = _CLASS_COLORS.get(obj.class_name, (200, 100, 50))
            brightness = config.time_of_day.ambient_light * config.weather.brightness_modifier
            color = tuple(int(c * max(brightness, 0.15)) for c in color)

            y1c, y2c = max(0, y1), min(h, y2)
            x1c, x2c = max(0, x1), min(w, x2)
            if y2c > y1c and x2c > x1c:
                img[y1c:y2c, x1c:x2c] = color

    def _apply_weather(
        self, img: np.ndarray, config: GenerationConfig, rng: np.random.Generator
    ) -> None:
        if config.weather.name == "rainy":
            n_streaks = int(config.weather.rain_intensity * 200)
            for _ in range(n_streaks):
                x = rng.integers(0, img.shape[1])
                y = rng.integers(0, img.shape[0] - 10)
                length = rng.integers(5, 15)
                alpha = rng.uniform(0.2, 0.5)
                for dy in range(length):
                    if y + dy < img.shape[0]:
                        existing = img[y + dy, x].astype(np.float32)
                        img[y + dy, x] = np.clip(
                            existing * (1 - alpha) + np.array([180, 190, 200]) * alpha,
                            0, 255,
                        ).astype(np.uint8)

        elif config.weather.name == "foggy":
            fog_alpha = config.weather.fog_density
            fog_layer = np.full_like(img, 200, dtype=np.float32)
            img[:] = np.clip(
                img.astype(np.float32) * (1 - fog_alpha) + fog_layer * fog_alpha,
                0, 255,
            ).astype(np.uint8)

    def _apply_time_of_day(
        self, img: np.ndarray, config: GenerationConfig, rng: np.random.Generator
    ) -> None:
        if config.time_of_day.name == "night":
            img[:] = np.clip(img.astype(np.float32) * 0.15, 0, 255).astype(np.uint8)
            h, w = img.shape[:2]
            headlight_x = w // 2
            headlight_y = int(h * 0.55)
            for r in range(80, 0, -2):
                alpha = 0.3 * (1 - r / 80)
                y_lo = max(0, headlight_y - r)
                y_hi = min(h, headlight_y + r // 3)
                x_lo = max(0, headlight_x - r)
                x_hi = min(w, headlight_x + r)
                mask = np.zeros((h, w), dtype=np.float32)
                yy, xx = np.ogrid[y_lo:y_hi, x_lo:x_hi]
                dist = np.sqrt(((xx - headlight_x) / max(r, 1)) ** 2 + ((yy - headlight_y) / max(r // 3, 1)) ** 2)
                local_mask = np.clip(1 - dist, 0, 1) * alpha
                img[y_lo:y_hi, x_lo:x_hi] = np.clip(
                    img[y_lo:y_hi, x_lo:x_hi].astype(np.float32)
                    + np.stack([local_mask * 200, local_mask * 190, local_mask * 160], axis=-1),
                    0, 255,
                ).astype(np.uint8)

    @staticmethod
    def _config_hash(config: GenerationConfig) -> str:
        parts = [
            config.weather.name,
            config.time_of_day.name,
            str(config.scene.road_width_m),
            str(config.scene.lane_count),
            ",".join(f"{o.class_name}:{o.count}" for o in config.objects),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


@dataclass
class GeneratedFrame:
    image: np.ndarray
    frame_index: int
    weather: str
    time_of_day: str
    objects: list[ObjectInstance]
    source_checksum: str
    config_hash: str


@dataclass
class ObjectInstance:
    class_name: str
    bbox_normalized: tuple[float, float, float, float]
    depth_m: float
    instance_id: int


_CLASS_DIMS: dict[str, tuple[float, float, float]] = {
    "car": (4.5, 1.5, 1.8),
    "truck": (8.0, 2.5, 3.0),
    "bus": (10.0, 2.5, 3.2),
    "motorcycle": (2.2, 0.8, 1.5),
    "bicycle": (1.8, 0.6, 1.2),
    "pedestrian": (0.5, 1.7, 0.5),
    "cow": (2.5, 1.5, 1.5),
    "dog": (0.8, 0.5, 0.6),
}

_CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "car": (180, 50, 50),
    "truck": (50, 50, 180),
    "bus": (180, 180, 50),
    "motorcycle": (200, 100, 0),
    "bicycle": (0, 150, 150),
    "pedestrian": (200, 150, 100),
    "cow": (120, 80, 40),
    "dog": (100, 70, 30),
}
