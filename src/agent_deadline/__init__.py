"""agent-deadline - cooperative per-task deadline primitive for agent workflows.

Agent loops chain LLM and tool calls. Each step has a per-call timeout,
but rarely a single wall-clock cap on the whole task. This library is a
small zero-dependency `Deadline` object that the loop checks between
steps and hands to downstream calls as their remaining timeout.

    from agent_deadline import Deadline, DeadlineExceeded

    deadline = Deadline.from_now(30.0)
    for step in agent_loop():
        deadline.check_or_raise()
        call_llm(prompt, timeout=deadline.remaining_seconds())

Use `intersect` to tighten a deadline for a nested operation:

    retry_deadline = task_deadline.intersect(5.0)

Use `Deadline.never()` as a default arg when no cap applies.
"""

from agent_deadline.deadline import Deadline, DeadlineExceeded

__version__ = "0.1.0"

__all__ = [
    "Deadline",
    "DeadlineExceeded",
    "__version__",
]
