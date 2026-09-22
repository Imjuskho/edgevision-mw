"""Bandwidth-aware scheduler for federated sync rounds.

Coordinates off-peak synchronization so FL updates don't compete
with the live WS inference path for device resources.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

logger = logging.getLogger("edgevision.federated.scheduler")


class SyncPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class SyncState(str, Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEFERRED = "deferred"


@dataclass
class SyncTask:
    """A federated sync task scheduled for execution."""

    task_id: str
    node_id: str
    priority: SyncPriority
    state: SyncState = SyncState.PENDING
    created_at: float = field(default_factory=time.time)
    scheduled_for: float | None = None
    started_at: float | None = None
    completed_at: float | None = None
    bandwidth_mbps: float | None = None
    retry_count: int = 0
    max_retries: int = 3
    estimated_bytes: int = 0
    error: str | None = None

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return end - self.started_at

    @property
    def wait_time(self) -> float:
        if self.scheduled_for is None:
            return 0.0
        start = self.started_at or time.time()
        return max(0, start - self.scheduled_for)


@dataclass
class DeviceResourceState:
    """Per-device resource state for scheduling decisions."""

    node_id: str
    current_inference_active: bool = False
    battery_voltage: float = 12.0
    solar_input_watts: float = 0.0
    storage_used_gb: float = 0.0
    storage_total_gb: float = 64.0
    lte_rssi_dbm: float = -70.0
    last_heartbeat: float | None = None
    bandwidth_mbps: float = 1.0
    is_charging: bool = False

    @property
    def battery_pct(self) -> float:
        # Typical 12V lead-acid: 12.6V=100%, 11.8V=0%
        return max(0, min(1, (self.battery_voltage - 11.8) / 0.8))

    @property
    def signal_quality(self) -> float:
        # Map RSSI to 0-1 quality: -50 dBm = excellent, -100 dBm = poor
        return max(0, min(1, (self.lte_rssi_dbm + 100) / 50))

    @property
    def is_offpeak(self) -> bool:
        """Heuristic: off-peak if not inferencing and battery is adequate."""
        return (
            not self.current_inference_active
            and self.battery_pct > 0.3
            and self.signal_quality > 0.2
        )


class BandwidthAwareScheduler:
    """Schedules FL sync tasks to avoid resource contention.

    Rules:
    1. Never schedule while the device is actively running live inference
    2. Prefer off-peak hours (configurable window, default 02:00-05:00)
    3. Respect battery constraints (don't sync on low battery)
    4. Defer during poor connectivity
    5. Priority queue with fair scheduling across devices
    """

    def __init__(
        self,
        offpeak_start_hour: int = 2,
        offpeak_end_hour: int = 5,
        min_battery_pct: float = 0.3,
        min_signal_quality: float = 0.2,
        max_concurrent_syncs: int = 1,
        max_bytes_per_sync: int = 50 * 1024 * 1024,  # 50 MB
    ):
        self.offpeak_start_hour = offpeak_start_hour
        self.offpeak_end_hour = offpeak_end_hour
        self.min_battery_pct = min_battery_pct
        self.min_signal_quality = min_signal_quality
        self.max_concurrent_syncs = max_concurrent_syncs
        self.max_bytes_per_sync = max_bytes_per_sync

        self._device_states: dict[str, DeviceResourceState] = {}
        self._task_queue: list[SyncTask] = []
        self._active_syncs: dict[str, SyncTask] = {}
        self._lock = threading.Lock()

    def update_device_state(self, state: DeviceResourceState) -> None:
        """Update resource state for a device (from heartbeat data)."""
        with self._lock:
            self._device_states[state.node_id] = state

    def can_sync_now(self, node_id: str) -> tuple[bool, str]:
        """Check if a device can sync right now.

        Returns (allowed, reason).
        """
        state = self._device_states.get(node_id)
        if state is None:
            return False, "unknown_device"

        if state.current_inference_active:
            return False, "inference_active"

        if state.battery_pct < self.min_battery_pct:
            return False, f"low_battery_{state.battery_pct:.0%}"

        if state.signal_quality < self.min_signal_quality:
            return False, f"poor_signal_{state.signal_quality:.0%}"

        if len(self._active_syncs) >= self.max_concurrent_syncs:
            return False, "max_concurrent_reached"

        return True, "ok"

    def is_offpeak(self) -> bool:
        """Check if current time is within the off-peak window."""
        now = datetime.now(UTC)
        hour = now.hour
        if self.offpeak_start_hour <= self.offpeak_end_hour:
            return self.offpeak_start_hour <= hour < self.offpeak_end_hour
        # Wraps midnight
        return hour >= self.offpeak_start_hour or hour < self.offpeak_end_hour

    def schedule_task(self, task: SyncTask) -> SyncTask:
        """Schedule a sync task, deferring if resources aren't available."""
        with self._lock:
            can_sync, reason = self.can_sync_now(task.node_id)

            if can_sync and self.is_offpeak():
                task.state = SyncState.SCHEDULED
                task.scheduled_for = time.time()
                logger.info(
                    "Scheduling sync %s for %s (off-peak, resources available)",
                    task.task_id,
                    task.node_id,
                )
            elif can_sync:
                # Can sync now but not off-peak — schedule for next off-peak
                task.state = SyncState.SCHEDULED
                task.scheduled_for = self._next_offpeak_timestamp()
                task.priority = SyncPriority.LOW
                logger.info(
                    "Deferring sync %s for %s to next off-peak window",
                    task.task_id,
                    task.node_id,
                )
            else:
                task.state = SyncState.DEFERRED
                task.scheduled_for = self._next_offpeak_timestamp()
                logger.info(
                    "Deferring sync %s for %s: %s",
                    task.task_id,
                    task.node_id,
                    reason,
                )

            self._task_queue.append(task)
            self._task_queue.sort(key=lambda t: (
                0 if t.priority == SyncPriority.HIGH else 1 if t.priority == SyncPriority.NORMAL else 2,
                t.scheduled_for or float("inf"),
            ))
            return task

    def get_ready_tasks(self) -> list[SyncTask]:
        """Return tasks that are ready to execute now."""
        now = time.time()
        ready = []
        with self._lock:
            for task in self._task_queue:
                if task.state == SyncState.SCHEDULED and (task.scheduled_for or 0) <= now:
                    can_sync, _ = self.can_sync_now(task.node_id)
                    if can_sync:
                        ready.append(task)
            return ready

    def start_task(self, task: SyncTask) -> None:
        """Mark a task as running."""
        with self._lock:
            task.state = SyncState.RUNNING
            task.started_at = time.time()
            self._active_syncs[task.task_id] = task

    def complete_task(self, task: SyncTask, success: bool, error: str | None = None) -> None:
        """Mark a task as completed or failed."""
        with self._lock:
            task.completed_at = time.time()
            if success:
                task.state = SyncState.COMPLETED
                self._task_queue = [t for t in self._task_queue if t.task_id != task.task_id]
            else:
                task.error = error
                task.retry_count += 1
                if task.retry_count >= task.max_retries:
                    task.state = SyncState.FAILED
                    self._task_queue = [t for t in self._task_queue if t.task_id != task.task_id]
                else:
                    task.state = SyncState.SCHEDULED
                    task.scheduled_for = self._next_offpeak_timestamp()
            self._active_syncs.pop(task.task_id, None)

    def estimate_transfer_time(self, task: SyncTask) -> float:
        """Estimate transfer time in seconds for a task."""
        state = self._device_states.get(task.node_id)
        if state is None or state.bandwidth_mbps <= 0:
            return float("inf")
        bits = task.estimated_bytes * 8
        return bits / (state.bandwidth_mbps * 1e6)

    def get_queue_status(self) -> dict:
        """Return current scheduler status."""
        with self._lock:
            return {
                "pending": len([t for t in self._task_queue if t.state == SyncState.PENDING]),
                "scheduled": len([t for t in self._task_queue if t.state == SyncState.SCHEDULED]),
                "running": len(self._active_syncs),
                "is_offpeak": self.is_offpeak(),
                "next_offpeak": datetime.fromtimestamp(
                    self._next_offpeak_timestamp(), UTC
                ).isoformat(),
                "device_count": len(self._device_states),
            }

    def _next_offpeak_timestamp(self) -> float:
        """Compute the next off-peak window start timestamp."""
        now = datetime.now(UTC)
        target = now.replace(
            hour=self.offpeak_start_hour, minute=0, second=0, microsecond=0
        )
        if target <= now:
            target += timedelta(days=1)
        return target.timestamp()
