import dataclasses
import math
import time

import pytest

from agent_deadline import Deadline, DeadlineExceeded

# ---------- factories ----------


def test_from_now_sets_at_relative_to_monotonic():
    before = time.monotonic()
    d = Deadline.from_now(0.5)
    after = time.monotonic()
    # d.at should be ~0.5s in the future from a time between before/after
    assert before + 0.5 <= d.at <= after + 0.5 + 1e-6


def test_from_now_negative_gives_already_expired_deadline():
    d = Deadline.from_now(-1.0)
    assert d.is_expired()
    assert d.remaining_seconds() == 0.0


def test_never_is_not_expired_and_remaining_is_inf():
    d = Deadline.never()
    assert d.is_never()
    assert not d.is_expired()
    assert d.remaining_seconds() == math.inf


def test_never_check_or_raise_is_noop():
    d = Deadline.never()
    # call several times, should never raise
    for _ in range(5):
        d.check_or_raise()


def test_constructor_directly_with_at_works():
    target = time.monotonic() + 1.0
    d = Deadline(at=target)
    assert d.at == target
    assert not d.is_expired()


# ---------- is_expired ----------


def test_is_expired_false_when_in_future():
    d = Deadline.from_now(10.0)
    assert not d.is_expired()


def test_is_expired_true_when_past():
    d = Deadline.from_now(0.001)
    time.sleep(0.01)
    assert d.is_expired()


# ---------- remaining_seconds ----------


def test_remaining_seconds_positive_when_in_future():
    d = Deadline.from_now(1.0)
    r = d.remaining_seconds()
    assert 0.0 < r <= 1.0


def test_remaining_seconds_zero_when_expired():
    d = Deadline.from_now(0.001)
    time.sleep(0.01)
    assert d.remaining_seconds() == 0.0


def test_remaining_seconds_never_negative():
    d = Deadline.from_now(-100.0)
    assert d.remaining_seconds() == 0.0


# ---------- check_or_raise ----------


def test_check_or_raise_does_not_raise_when_in_future():
    d = Deadline.from_now(5.0)
    d.check_or_raise()  # should not raise


def test_check_or_raise_raises_when_past():
    d = Deadline.from_now(0.001)
    time.sleep(0.01)
    with pytest.raises(DeadlineExceeded) as exc:
        d.check_or_raise()
    assert exc.value.deadline is d
    assert exc.value.elapsed_seconds > 0.0


def test_deadline_exceeded_carries_elapsed():
    d = Deadline.from_now(0.001)
    time.sleep(0.02)
    try:
        d.check_or_raise()
    except DeadlineExceeded as e:
        assert e.elapsed_seconds >= 0.02
        assert "deadline exceeded" in str(e)


# ---------- elapsed_seconds ----------


def test_elapsed_seconds_counts_up():
    d = Deadline.from_now(10.0)
    e1 = d.elapsed_seconds()
    time.sleep(0.02)
    e2 = d.elapsed_seconds()
    assert e2 > e1
    assert e2 - e1 >= 0.02


def test_elapsed_seconds_starts_near_zero():
    d = Deadline.from_now(10.0)
    assert d.elapsed_seconds() < 0.05


# ---------- intersect ----------


def test_intersect_picks_tighter_when_other_sooner():
    parent = Deadline.from_now(60.0)
    child = parent.intersect(1.0)
    # child should expire ~1s from now, well before parent's 60s
    assert child.remaining_seconds() <= 1.0
    assert child.at < parent.at


def test_intersect_keeps_parent_when_other_later():
    parent = Deadline.from_now(1.0)
    child = parent.intersect(60.0)
    # child should still expire near parent (1s), not 60s
    assert child.at == parent.at


def test_intersect_with_never_keeps_self():
    parent = Deadline.from_now(5.0)
    child = parent.intersect(math.inf)
    assert child.at == parent.at


def test_intersect_preserves_created_at_for_elapsed():
    parent = Deadline.from_now(60.0)
    time.sleep(0.02)
    child = parent.intersect(1.0)
    # elapsed should reflect parent's start, not child's
    assert child.elapsed_seconds() >= 0.02


# ---------- intersect_deadline ----------


def test_intersect_deadline_picks_tighter():
    a = Deadline.from_now(10.0)
    b = Deadline.from_now(1.0)
    out = a.intersect_deadline(b)
    assert out.at == b.at  # b is tighter


def test_intersect_deadline_with_never_keeps_self():
    finite = Deadline.from_now(5.0)
    never = Deadline.never()
    out = finite.intersect_deadline(never)
    assert out.at == finite.at


def test_intersect_deadline_never_with_finite_picks_finite():
    never = Deadline.never()
    finite = Deadline.from_now(5.0)
    out = never.intersect_deadline(finite)
    # min(inf, finite_at) == finite_at
    assert out.at == finite.at


# ---------- context manager ----------


def test_context_manager_enters_when_alive():
    d = Deadline.from_now(5.0)
    with d as inner:
        assert inner is d
        assert not inner.is_expired()


def test_context_manager_raises_on_enter_if_already_expired():
    d = Deadline.from_now(0.001)
    time.sleep(0.01)
    with pytest.raises(DeadlineExceeded), d:
        # body must not run
        raise AssertionError("body should not execute")


def test_context_manager_does_not_auto_raise_on_exit():
    # Build a 50ms deadline, sleep past it inside the block. We expect NO
    # exception on exit because the model is cooperative; only an explicit
    # check_or_raise inside would fire.
    d = Deadline.from_now(0.05)
    with d:
        time.sleep(0.1)
    # if we got here, no auto-raise happened
    assert d.is_expired()


def test_context_manager_does_not_suppress_inner_exceptions():
    d = Deadline.from_now(5.0)
    with pytest.raises(RuntimeError, match="inner"), d:
        raise RuntimeError("inner")


# ---------- immutability ----------


def test_deadline_is_frozen():
    d = Deadline.from_now(5.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.at = 0.0  # type: ignore[misc]
