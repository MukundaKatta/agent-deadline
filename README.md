# agent-deadline

[![PyPI](https://img.shields.io/pypi/v/agent-deadline.svg)](https://pypi.org/project/agent-deadline/)
[![Python](https://img.shields.io/pypi/pyversions/agent-deadline.svg)](https://pypi.org/project/agent-deadline/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Cooperative per-task deadline primitive for agent workflows.**

Agent loops chain LLM calls and tool calls. Each step has its own
network timeout, but there is rarely a single wall-clock cap on the
whole task. This library is a small, zero-dependency `Deadline` object
that the loop checks between steps and hands to downstream calls as
their remaining timeout.

Cooperative: code checks the deadline. Nothing is preempted.

## Install

```bash
pip install agent-deadline
```

## Use

```python
from agent_deadline import Deadline, DeadlineExceeded

deadline = Deadline.from_now(30.0)  # 30 seconds for the whole task

for step in agent_loop():
    deadline.check_or_raise()
    result = call_llm(prompt, timeout=deadline.remaining_seconds())
    run_tool(result.tool_call, timeout=deadline.remaining_seconds())
```

`check_or_raise()` raises `DeadlineExceeded` when the clock has passed
the deadline. Catch it at the top of the loop to return a partial
result instead of hanging on the next call.

## Nested operations: intersect

A sub-step often has its own soft cap that should never exceed the
parent task's remaining time. `intersect` picks the tighter of the two.

```python
task_deadline = Deadline.from_now(30.0)

# this retry block should not run longer than 5 seconds, AND not run past
# the parent task deadline whichever is sooner
retry_deadline = task_deadline.intersect(5.0)

while not retry_deadline.is_expired():
    try:
        return call_flaky_thing(timeout=retry_deadline.remaining_seconds())
    except TransientError:
        time.sleep(0.5)
```

You can also intersect two `Deadline` objects directly with
`intersect_deadline(other)`.

## Async

`remaining_seconds()` plugs straight into `asyncio.wait_for`.

```python
deadline = Deadline.from_now(30.0)

try:
    result = await asyncio.wait_for(
        call_llm_async(prompt),
        timeout=deadline.remaining_seconds(),
    )
except asyncio.TimeoutError:
    deadline.check_or_raise()  # converts to DeadlineExceeded if past
    raise                       # otherwise it was a per-call timeout, not the task one
```

## Context manager

`with` form refuses to enter an already-expired block, but does NOT
auto-raise on exit. This stays cooperative: only the checks the caller
writes can fire.

```python
with Deadline.from_now(10.0) as d:
    do_work(timeout=d.remaining_seconds())
```

If `d` was already expired at `__enter__`, the block raises
`DeadlineExceeded` instead of running.

## Never expires

`Deadline.never()` is a sentinel for default args. `remaining_seconds`
returns `math.inf`, `is_expired()` is always `False`, and
`check_or_raise()` is a no-op.

```python
def run_step(deadline: Deadline = Deadline.never()):
    deadline.check_or_raise()
    ...
```

## Siblings

`agent-deadline` is the time axis. Pair with the cost and rate axes:

- [`token-budget-py`](https://pypi.org/project/token-budget-py/) — token + USD cap for the whole fan-out
- [`llm-budget-window`](https://crates.io/crates/llm-budget-window) — time-windowed token cap (per minute / hour / day)
- [`llm-retry-py`](https://pypi.org/project/llm-retry-py/) — exponential backoff retry, runs nicely inside a `Deadline`

## What it does NOT do

- No preemption. Threads / coroutines are not interrupted. The caller
  has to check `is_expired()` or call `check_or_raise()` between steps.
- No wall-clock dependency. Uses `time.monotonic()` so deadlines are
  unaffected by NTP jumps and clock resets.
- No async runtime lock-in. Works under `asyncio`, `trio`, threads, sync.
- No HTTP. Doesn't talk to any LLM provider.

## License

MIT
