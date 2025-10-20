"""
Test utility helpers for VoxBridge testing
"""
import asyncio
from typing import Any, Callable, Optional
from unittest.mock import AsyncMock


# ============================================================
# Async Helpers
# ============================================================

async def wait_for_condition(
    condition: Callable[[], bool],
    timeout: float = 5.0,
    interval: float = 0.1
) -> bool:
    """
    Wait for a condition to become true

    Args:
        condition: Function that returns True when condition is met
        timeout: Maximum time to wait in seconds
        interval: Check interval in seconds

    Returns:
        True if condition was met, False if timeout

    Usage:
        await wait_for_condition(lambda: client.is_connected, timeout=2.0)
    """
    elapsed = 0.0
    while elapsed < timeout:
        if condition():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return False


async def wait_for_async_condition(
    condition: Callable[[], Any],
    timeout: float = 5.0,
    interval: float = 0.1
) -> bool:
    """
    Wait for an async condition to become true

    Args:
        condition: Async function that returns True when condition is met
        timeout: Maximum time to wait in seconds
        interval: Check interval in seconds

    Returns:
        True if condition was met, False if timeout
    """
    elapsed = 0.0
    while elapsed < timeout:
        if await condition():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return False


async def wait_for_tasks(timeout: float = 1.0):
    """
    Wait for all pending tasks to complete

    Args:
        timeout: Maximum time to wait

    Usage:
        await wait_for_tasks(timeout=2.0)
    """
    try:
        tasks = [t for t in asyncio.all_tasks()
                 if not t.done() and t != asyncio.current_task()]
        if tasks:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
    except asyncio.TimeoutError:
        pass


# ============================================================
# Mock Helpers
# ============================================================

def create_async_mock(return_value: Any = None, **kwargs) -> AsyncMock:
    """
    Create an AsyncMock with optional return value

    Args:
        return_value: Value to return when called
        **kwargs: Additional arguments for AsyncMock

    Returns:
        Configured AsyncMock

    Usage:
        mock_func = create_async_mock(return_value="test")
        result = await mock_func()  # Returns "test"
    """
    return AsyncMock(return_value=return_value, **kwargs)


def create_async_mock_iterator(items: list) -> AsyncMock:
    """
    Create an async mock iterator

    Args:
        items: List of items to iterate over

    Returns:
        AsyncMock that can be used with async for

    Usage:
        mock_stream = create_async_mock_iterator([b'chunk1', b'chunk2'])
        async for chunk in mock_stream:
            print(chunk)
    """
    async def async_iterator():
        for item in items:
            yield item

    mock = AsyncMock()
    mock.__aiter__.return_value = async_iterator()
    return mock


# ============================================================
# Assertion Helpers
# ============================================================

def assert_called_with_partial(mock: AsyncMock, **expected_kwargs):
    """
    Assert mock was called with at least the specified kwargs

    Args:
        mock: Mock to check
        **expected_kwargs: Expected keyword arguments

    Raises:
        AssertionError: If mock wasn't called with expected kwargs

    Usage:
        assert_called_with_partial(mock_send, text="hello")
    """
    assert mock.called, "Mock was not called"

    for call in mock.call_args_list:
        call_kwargs = call.kwargs
        if all(call_kwargs.get(k) == v for k, v in expected_kwargs.items()):
            return

    raise AssertionError(
        f"Mock was not called with expected kwargs: {expected_kwargs}\n"
        f"Actual calls: {mock.call_args_list}"
    )


async def assert_eventually(
    condition: Callable[[], bool],
    timeout: float = 2.0,
    message: str = "Condition not met within timeout"
):
    """
    Assert that a condition becomes true within timeout

    Args:
        condition: Function that should eventually return True
        timeout: Maximum time to wait
        message: Error message if assertion fails

    Raises:
        AssertionError: If condition doesn't become true

    Usage:
        await assert_eventually(lambda: len(results) > 0, timeout=1.0)
    """
    result = await wait_for_condition(condition, timeout=timeout)
    assert result, message


# ============================================================
# Data Generators
# ============================================================

def generate_user_id(index: int = 0) -> str:
    """Generate test Discord user ID"""
    return str(100000000 + index)


def generate_channel_id(index: int = 0) -> str:
    """Generate test Discord channel ID"""
    return str(500000000 + index)


def generate_guild_id(index: int = 0) -> str:
    """Generate test Discord guild ID"""
    return str(900000000 + index)


def generate_timestamp() -> str:
    """Generate ISO timestamp for testing"""
    from datetime import datetime
    return datetime.now().isoformat()


# ============================================================
# Context Managers
# ============================================================

class TimedContext:
    """
    Context manager for measuring execution time

    Usage:
        async with TimedContext() as timer:
            await some_async_function()
        assert timer.elapsed < 1.0, "Too slow!"
    """

    def __init__(self):
        self.start = 0.0
        self.end = 0.0
        self.elapsed = 0.0

    async def __aenter__(self):
        self.start = asyncio.get_event_loop().time()
        return self

    async def __aexit__(self, *args):
        self.end = asyncio.get_event_loop().time()
        self.elapsed = self.end - self.start


# ============================================================
# Test Data Helpers
# ============================================================

def chunk_bytes(data: bytes, chunk_size: int) -> list[bytes]:
    """
    Split bytes into chunks

    Args:
        data: Bytes to split
        chunk_size: Size of each chunk

    Returns:
        List of byte chunks
    """
    return [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]


async def collect_async_iterator(iterator, max_items: int = 100) -> list:
    """
    Collect items from async iterator into list

    Args:
        iterator: Async iterator
        max_items: Maximum items to collect

    Returns:
        List of collected items

    Usage:
        chunks = await collect_async_iterator(response.aiter_bytes())
    """
    items = []
    count = 0
    async for item in iterator:
        items.append(item)
        count += 1
        if count >= max_items:
            break
    return items


# ============================================================
# Environment Helpers
# ============================================================

def get_test_env_var(key: str, default: str = "") -> str:
    """
    Get test environment variable with TEST_ prefix

    Args:
        key: Environment variable key
        default: Default value if not set

    Returns:
        Environment variable value
    """
    import os
    return os.getenv(f"TEST_{key}", os.getenv(key, default))


def set_test_env_vars(**kwargs):
    """
    Set multiple test environment variables

    Usage:
        set_test_env_vars(
            DISCORD_TOKEN="test_token",
            N8N_WEBHOOK_URL="http://localhost:8888"
        )
    """
    import os
    for key, value in kwargs.items():
        os.environ[key] = str(value)
