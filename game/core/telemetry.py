"""Shared telemetry primitives for multi-game validator/miner flows."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import time
from typing import Any, Dict, Iterator, Optional, Protocol


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class TelemetryEvent:
    """Structured event emitted by core runtime or a game plugin."""

    name: str
    ts_ms: int
    game_code: str
    session_id: Optional[str] = None
    attempt_id: Optional[str] = None
    miner_hotkey: Optional[str] = None
    fields: Dict[str, Any] = field(default_factory=dict)


class TelemetrySink(Protocol):
    def emit(self, event: TelemetryEvent) -> None: ...


class NullTelemetrySink:
    """Default no-op sink used until telemetry wiring is added."""

    def emit(self, event: TelemetryEvent) -> None:
        return


@dataclass
class LatencyTimer:
    """Small helper for measuring durations in milliseconds."""

    started_perf: float = field(default_factory=time.perf_counter)

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started_perf) * 1000)

    def reset(self) -> None:
        self.started_perf = time.perf_counter()


def make_event(
    *,
    name: str,
    game_code: str,
    session_id: Optional[str] = None,
    attempt_id: Optional[str] = None,
    miner_hotkey: Optional[str] = None,
    fields: Optional[Dict[str, Any]] = None,
) -> TelemetryEvent:
    return TelemetryEvent(
        name=name,
        ts_ms=now_ms(),
        game_code=(game_code or "").strip().lower(),
        session_id=session_id,
        attempt_id=attempt_id,
        miner_hotkey=miner_hotkey,
        fields=dict(fields or {}),
    )


@contextmanager
def timed(timer: Optional[LatencyTimer] = None) -> Iterator[LatencyTimer]:
    """Context manager for measuring a code block.

    Example:
        with timed() as t:
            ...
        elapsed = t.elapsed_ms()
    """
    t = timer or LatencyTimer()
    yield t
