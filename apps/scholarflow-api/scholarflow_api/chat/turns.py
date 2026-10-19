"""In-process turn lifecycle registry (Phase 8.3).

Single API process only — not distributed. Provides cancel flags and
active-turn lookup for SSE disconnect / explicit cancel.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

TurnPhase = Literal["running", "cancelling", "finished"]


@dataclass
class TurnHandle:
    turn_id: str
    conversation_id: str
    created_at: float = field(default_factory=time.monotonic)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    phase: TurnPhase = "running"
    error: str | None = None

    def request_cancel(self) -> None:
        self.phase = "cancelling"
        self.cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()


class TurnRegistry:
    """Track active turns in the current process."""

    def __init__(self, *, max_active: int = 8, max_duration_seconds: float = 300.0) -> None:
        self._lock = threading.RLock()
        self._active: dict[str, TurnHandle] = {}
        self.max_active = max_active
        self.max_duration_seconds = max_duration_seconds

    def begin(self, conversation_id: str) -> TurnHandle:
        with self._lock:
            # Drop finished leftovers
            self._active = {
                k: v for k, v in self._active.items() if v.phase != "finished"
            }
            if len(self._active) >= self.max_active:
                raise RuntimeError(
                    f"Too many active turns ({self.max_active}); try again later"
                )
            handle = TurnHandle(
                turn_id=f"turn-{uuid.uuid4().hex[:12]}",
                conversation_id=conversation_id,
            )
            self._active[handle.turn_id] = handle
            return handle

    def get(self, turn_id: str) -> TurnHandle | None:
        with self._lock:
            return self._active.get(turn_id)

    def cancel(self, turn_id: str) -> bool:
        with self._lock:
            handle = self._active.get(turn_id)
            if handle is None:
                return False
            handle.request_cancel()
            return True

    def finish(self, turn_id: str) -> None:
        with self._lock:
            handle = self._active.get(turn_id)
            if handle is not None:
                handle.phase = "finished"
                # Keep briefly for cancel race, then drop
                self._active.pop(turn_id, None)

    def timed_out(self, handle: TurnHandle) -> bool:
        return (time.monotonic() - handle.created_at) > self.max_duration_seconds


# Process-wide default registry (single uvicorn worker assumption)
default_turn_registry = TurnRegistry()
