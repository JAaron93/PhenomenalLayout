from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass
class OpStats:
    count: int = 0
    success: int = 0
    total_ms: float = 0.0


class MonitoringService:
    """Lightweight performance and error monitoring.

    Tracks operation metrics and keeps a rolling window of recent events to
    compute error rates and percentile latencies. Uses standard logging.
    """

    def __init__(
        self,
        window_seconds: int = 300,
        logger: logging.Logger | None = None,
    ) -> None:
        self.window_seconds = window_seconds
        self.logger = logger or logging.getLogger("dolphin_ocr.monitoring")
        self._events: deque[tuple[float, str, bool, float, str | None]] = deque()
        self._op_stats: dict[str, OpStats] = defaultdict(OpStats)
        self._op_latencies: dict[str, deque[tuple[float, float]]] = defaultdict(deque)

    # --------------------------- Recording ---------------------------
    def record_operation(
        self,
        operation: str,
        duration_ms: float,
        *,
        success: bool,
        error_code: str | None = None,
    ) -> None:
        now = time.time()
        self._events.append((now, operation, success, duration_ms, error_code))
        self._prune(now)

        stats = self._op_stats[operation]
        stats.count += 1
        stats.total_ms += float(duration_ms)
        if success:
            stats.success += 1

        lat_q = self._op_latencies[operation]
        lat_q.append((now, float(duration_ms)))
        self._prune_latencies(operation, now)

    # --------------------------- Queries ----------------------------
    def get_error_rate(self, *, window_seconds: int | None = None) -> float:
        ws = window_seconds or self.window_seconds
        cutoff = time.time() - ws
        total = 0
        errors = 0
        for ts, _op, success, _dur, _code in self._events:
            if ts >= cutoff:
                total += 1
                if not success:
                    errors += 1
        return 0.0 if total == 0 else float(errors) / float(total)

    def get_p95_latency(
        self, operation: str, *, window_seconds: int | None = None
    ) -> float:
        now = time.time()
        samples = self._latencies_in_window(operation, window_seconds, now=now)
        if not samples:
            return 0.0
        values = sorted(samples)
        idx = int(0.95 * (len(values) - 1))
        return float(values[idx])

    def get_summary(self) -> dict[str, object]:
        out: dict[str, object] = {}
        for op, st in self._op_stats.items():
            avg = 0.0 if st.count == 0 else st.total_ms / float(st.count)
            out[op] = {
                "count": st.count,
                "success": st.success,
                "avg_ms": float(avg),
            }
        out["error_rate"] = float(self.get_error_rate())
        return out

    # ---------------------------- Logging ---------------------------
    def log_health(self) -> None:
        summary = self.get_summary()
        self.logger.info("health: %s", summary)

    # --------------------------- Internals --------------------------
    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def _prune_latencies(self, operation: str, now: float) -> None:
        cutoff = now - self.window_seconds
        q = self._op_latencies[operation]
        while q and q[0][0] < cutoff:
            q.popleft()

    def _latencies_in_window(
        self,
        operation: str,
        window_seconds: int | None,
        now: float | None = None,
    ) -> Iterable[float]:
        ws = window_seconds or self.window_seconds
        current_time = time.time() if now is None else now
        cutoff = current_time - ws
        return [lat for ts, lat in self._op_latencies[operation] if ts >= cutoff]
