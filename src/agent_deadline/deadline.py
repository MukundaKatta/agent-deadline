"""Core Deadline implementation."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import ClassVar


class DeadlineExceeded(Exception):
    """Raised when `check_or_raise()` runs after the deadline has passed.

    Attributes:
        deadline: the Deadline object that fired
        elapsed_seconds: seconds since the deadline was created
    """

    def __init__(self, deadline: Deadline, elapsed_seconds: float):
        self.deadline = deadline
        self.elapsed_seconds = elapsed_seconds
        super().__init__(
            f"deadline exceeded: elapsed {elapsed_seconds:.6g}s past the configured cap"
        )


@dataclass(frozen=True)
class Deadline:
    """A monotonic-time deadline for cooperative task cancellation.

    `at` is an absolute monotonic timestamp (as returned by `time.monotonic()`).
    The companion `from_now` factory builds one from a duration in seconds.
    `never` builds one that never expires; its `remaining_seconds()` is `math.inf`.

    Deadlines are immutable. To tighten a deadline for a nested operation,
    use `intersect(other_seconds)` or `intersect_deadline(other)`.
    """

    at: float
    # creation time, captured at build time so elapsed_seconds works without
    # the caller having to remember when they made the deadline.
    _created_at: float = field(default_factory=time.monotonic)

    # Sentinel value used by `never()` to mean "no deadline".
    _NEVER_AT: ClassVar[float] = math.inf

    # ---- factories ----

    @classmethod
    def from_now(cls, seconds: float) -> Deadline:
        """Build a deadline `seconds` from now (monotonic clock).

        Negative `seconds` is allowed and produces an already-expired deadline,
        which is occasionally useful in tests.
        """
        now = time.monotonic()
        return cls(at=now + float(seconds), _created_at=now)

    @classmethod
    def never(cls) -> Deadline:
        """A deadline that never expires. Useful as a default argument."""
        now = time.monotonic()
        return cls(at=cls._NEVER_AT, _created_at=now)

    # ---- introspection ----

    def is_never(self) -> bool:
        """True if this deadline was built with `Deadline.never()`."""
        return self.at == self._NEVER_AT

    def is_expired(self) -> bool:
        """True if the current monotonic time is at or past `self.at`."""
        if self.is_never():
            return False
        return time.monotonic() >= self.at

    def remaining_seconds(self) -> float:
        """Seconds left until the deadline. Floor of zero (never negative).

        Returns `math.inf` for `Deadline.never()`. Hand this directly to
        `asyncio.wait_for(timeout=...)` or any other timeout-taking call.
        """
        if self.is_never():
            return math.inf
        remaining = self.at - time.monotonic()
        return remaining if remaining > 0.0 else 0.0

    def elapsed_seconds(self) -> float:
        """Seconds since this Deadline was constructed."""
        return time.monotonic() - self._created_at

    # ---- cooperative check ----

    def check_or_raise(self) -> None:
        """Raise `DeadlineExceeded` if the deadline has passed.

        No-op for `Deadline.never()`. Call this between steps in your loop.
        """
        if self.is_never():
            return
        now = time.monotonic()
        if now >= self.at:
            raise DeadlineExceeded(self, now - self._created_at)

    # ---- combinators ----

    def intersect(self, other_seconds: float) -> Deadline:
        """Return a new Deadline that is the tighter of `self` and
        `from_now(other_seconds)`.

        Use this for sub-steps that have their own soft cap but must never
        exceed the parent task's remaining time.
        """
        candidate = Deadline.from_now(other_seconds)
        return self.intersect_deadline(candidate)

    def intersect_deadline(self, other: Deadline) -> Deadline:
        """Return a new Deadline whose `at` is the minimum of self.at and other.at.

        `_created_at` is preserved from `self` so `elapsed_seconds()` keeps
        measuring against the original task start, not the intersection point.
        """
        tighter_at = min(self.at, other.at)
        return Deadline(at=tighter_at, _created_at=self._created_at)

    # ---- context manager ----

    def __enter__(self) -> Deadline:
        # Refuse to enter an already-expired block. The body never runs in
        # that case, so the caller cannot accidentally do real work past the
        # deadline at the moment of entry.
        self.check_or_raise()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Cooperative model: we do NOT auto-raise on exit. The body must
        # opt-in to checks. We don't suppress any exception raised inside.
        return None
