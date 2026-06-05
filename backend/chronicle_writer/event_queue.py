"""Real-time SSE event queue for token streaming within long-running LangGraph nodes.

Usage:
  from chronicle_writer.event_queue import init_queue, push_event, clear_queue

  # Before graph execution:
  queue = asyncio.Queue()
  init_queue(queue)

  # Inside a node function, push a token event:
  await push_event({"type": "token", "text": "..."})

  # After graph execution:
  clear_queue()
"""

import asyncio

_queue: asyncio.Queue | None = None


def init_queue(queue: asyncio.Queue) -> None:
    """Initialize the module-level queue reference."""
    global _queue
    _queue = queue


def get_queue() -> asyncio.Queue | None:
    """Get the current queue, or None if not initialized."""
    return _queue


def clear_queue() -> None:
    """Clear the module-level queue reference."""
    global _queue
    _queue = None


async def push_event(event: dict) -> None:
    """Push an event to the queue for real-time SSE streaming.

    Uses put_nowait internally — does not block the caller.
    Safe to call from within LangGraph node functions.
    """
    q = _queue
    if q is not None:
        q.put_nowait(event)
