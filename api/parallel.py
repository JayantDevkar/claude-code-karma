"""
Parallel processing utilities for session endpoints.

Phase 4 optimization: Process subagents and sessions concurrently.
"""

import asyncio
import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, List, TypeVar

logger = logging.getLogger(__name__)

# Shared thread pool for file I/O operations
# Using 16 workers for better I/O parallelism (I/O bound, not CPU bound)
_io_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="phase4_io")

T = TypeVar("T")
R = TypeVar("R")


async def run_in_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Run a synchronous function in the thread pool.

    Args:
        func: Synchronous function to execute
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function

    Returns:
        Result of the function execution
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_io_executor, functools.partial(func, *args, **kwargs))


async def process_items_parallel(
    items: List[T],
    processor: Callable[[T], R],
    max_concurrent: int = 4,
) -> List[R]:
    """
    Process multiple items in parallel using a thread pool.

    Args:
        items: List of items to process
        processor: Function to apply to each item
        max_concurrent: Maximum number of concurrent tasks

    Returns:
        List of processed results (exceptions filtered out)
    """
    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_semaphore(item: T) -> R:
        async with semaphore:
            return await run_in_thread(processor, item)

    tasks = [process_with_semaphore(item) for item in items]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and return successful results
    successes = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.warning("Failed to process item %d: %s", i, r)
        else:
            successes.append(r)
    return successes


def process_subagent_data(subagent: Any) -> dict:
    """
    Extract data from a single subagent.

    This function runs in a thread pool for parallel processing.

    Args:
        subagent: Agent instance to process

    Returns:
        Dict with extracted subagent data
    """
    from collections import Counter

    from models import AssistantMessage, ToolUseBlock, UserMessage
    from utils import extract_prompt_from_content

    tool_counts: Counter = Counter()
    initial_prompt = None
    message_count = 0

    for msg in subagent.iter_messages():
        message_count += 1
        if isinstance(msg, UserMessage):
            if initial_prompt is None and msg.content:
                prompt = extract_prompt_from_content(msg.content)
                if prompt:
                    initial_prompt = prompt[:5000]
        elif isinstance(msg, AssistantMessage):
            for block in msg.content_blocks:
                if isinstance(block, ToolUseBlock):
                    tool_counts[block.name] += 1

    return {
        "agent_id": subagent.agent_id,
        "slug": subagent.slug,
        "tool_counts": dict(tool_counts),
        "initial_prompt": initial_prompt,
        "message_count": message_count,
    }


async def process_subagents_parallel(subagents: List[Any]) -> List[dict]:
    """
    Process multiple subagents in parallel.

    Phase 4 optimization: Uses thread pool to process subagent JSONL files
    concurrently instead of sequentially.

    Args:
        subagents: List of Agent instances

    Returns:
        List of processed subagent data dicts
    """
    return await process_items_parallel(subagents, process_subagent_data, max_concurrent=4)


def shutdown_executor():
    """Shutdown the thread pool executor gracefully."""
    _io_executor.shutdown(wait=True)
