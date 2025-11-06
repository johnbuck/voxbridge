"""
Streaming Configuration Module

Global defaults for sentence-level streaming features.
Loaded from environment variables with sensible fallback defaults.

Architecture:
- Global defaults (this module) → TTS provider config → Runtime usage
"""

import os
from dataclasses import dataclass
from typing import Literal


@dataclass
class StreamingConfig:
    """
    Configuration for LLM response streaming features.

    Controls how LLM text responses are chunked and sent to TTS.
    Similar to Chatterbox TTS streaming but operates at the response level.
    """

    # Enable/disable response streaming
    enabled: bool = True

    # Chunking strategy for breaking up LLM responses
    # - 'sentence': Split on sentence boundaries (periods, !, ?)
    # - 'paragraph': Split on paragraph boundaries (double newlines)
    # - 'word': Split on word boundaries (spaces) - very granular
    # - 'fixed': Split at fixed character intervals
    chunking_strategy: Literal['sentence', 'paragraph', 'word', 'fixed'] = 'sentence'

    # Minimum chunk length before TTS synthesis (characters)
    # Shorter chunks are buffered with next chunk to avoid choppy audio
    min_chunk_length: int = 10

    # Maximum concurrent TTS synthesis requests
    # Controls how many chunks can be synthesized in parallel
    max_concurrent_tts: int = 3

    # Error handling strategy when TTS synthesis fails
    # - 'skip': Skip failed chunk and continue
    # - 'retry': Retry synthesis once before skipping
    # - 'fallback': Use backup TTS provider/voice
    error_strategy: Literal['skip', 'retry', 'fallback'] = 'retry'

    # User interruption strategy (when user starts speaking mid-response)
    # - 'immediate': Stop immediately, cancel all queued audio
    # - 'graceful': Finish current chunk, cancel rest
    # - 'drain': Finish current + next 1-2 chunks, then stop
    interruption_strategy: Literal['immediate', 'graceful', 'drain'] = 'graceful'

    def validate(self) -> None:
        """Validate configuration values."""
        if not 5 <= self.min_chunk_length <= 200:
            raise ValueError("min_chunk_length must be between 5 and 200")
        if not 1 <= self.max_concurrent_tts <= 8:
            raise ValueError("max_concurrent_tts must be between 1 and 8")
        if self.chunking_strategy not in ['sentence', 'paragraph', 'word', 'fixed']:
            raise ValueError("chunking_strategy must be 'sentence', 'paragraph', 'word', or 'fixed'")
        if self.error_strategy not in ['skip', 'retry', 'fallback']:
            raise ValueError("error_strategy must be 'skip', 'retry', or 'fallback'")
        if self.interruption_strategy not in ['immediate', 'graceful', 'drain']:
            raise ValueError("interruption_strategy must be 'immediate', 'graceful', or 'drain'")


def load_streaming_config() -> StreamingConfig:
    """
    Load streaming configuration from environment variables.

    Environment Variables:
        STREAMING_ENABLED: Enable response streaming (default: true)
        STREAMING_CHUNKING_STRATEGY: Chunking strategy (default: sentence)
        STREAMING_MIN_CHUNK_LENGTH: Min chars per chunk (default: 10)
        STREAMING_MAX_CONCURRENT_TTS: Max parallel TTS requests (default: 3)
        STREAMING_ERROR_STRATEGY: Error handling (default: retry)
        STREAMING_INTERRUPTION_STRATEGY: Interruption handling (default: graceful)

    Returns:
        StreamingConfig with values loaded from environment or defaults
    """
    config = StreamingConfig(
        enabled=os.getenv('STREAMING_ENABLED', 'true').lower() in ['true', '1', 'yes'],
        chunking_strategy=os.getenv('STREAMING_CHUNKING_STRATEGY', 'sentence'),  # type: ignore
        min_chunk_length=int(os.getenv('STREAMING_MIN_CHUNK_LENGTH', '10')),
        max_concurrent_tts=int(os.getenv('STREAMING_MAX_CONCURRENT_TTS', '3')),
        error_strategy=os.getenv('STREAMING_ERROR_STRATEGY', 'retry'),  # type: ignore
        interruption_strategy=os.getenv('STREAMING_INTERRUPTION_STRATEGY', 'graceful'),  # type: ignore
    )

    config.validate()
    return config


# Global singleton instance
_streaming_config: StreamingConfig | None = None

# Runtime overrides (in-memory, reset on restart)
_runtime_overrides: StreamingConfig | None = None


def get_streaming_config() -> StreamingConfig:
    """
    Get global streaming configuration singleton.

    Priority:
    1. Runtime overrides (set via update_streaming_config)
    2. Environment variables (loaded on first call)

    Returns:
        StreamingConfig singleton or runtime override
    """
    global _streaming_config, _runtime_overrides

    # Return runtime overrides if set
    if _runtime_overrides is not None:
        return _runtime_overrides

    # Otherwise load from environment (cached)
    if _streaming_config is None:
        _streaming_config = load_streaming_config()
    return _streaming_config


def update_streaming_config(
    enabled: bool | None = None,
    chunking_strategy: str | None = None,
    min_chunk_length: int | None = None,
    max_concurrent_tts: int | None = None,
    error_strategy: str | None = None,
    interruption_strategy: str | None = None,
) -> StreamingConfig:
    """
    Update streaming configuration at runtime.

    Args:
        enabled: Enable/disable response streaming
        chunking_strategy: Chunking strategy (sentence/paragraph/word/fixed)
        min_chunk_length: Minimum chunk length (5-200)
        max_concurrent_tts: Maximum concurrent TTS requests (1-8)
        error_strategy: Error handling strategy (skip/retry/fallback)
        interruption_strategy: Interruption handling (immediate/graceful/drain)

    Returns:
        Updated StreamingConfig

    Raises:
        ValueError: If validation fails

    Note:
        Changes persist until container restart. Environment variables
        provide defaults that are restored on restart.
    """
    global _runtime_overrides

    # Get current config (either override or env default)
    current = get_streaming_config()

    # Create new config with updates
    new_config = StreamingConfig(
        enabled=enabled if enabled is not None else current.enabled,
        chunking_strategy=chunking_strategy if chunking_strategy is not None else current.chunking_strategy,  # type: ignore
        min_chunk_length=min_chunk_length if min_chunk_length is not None else current.min_chunk_length,
        max_concurrent_tts=max_concurrent_tts if max_concurrent_tts is not None else current.max_concurrent_tts,
        error_strategy=error_strategy if error_strategy is not None else current.error_strategy,  # type: ignore
        interruption_strategy=interruption_strategy if interruption_strategy is not None else current.interruption_strategy,  # type: ignore
    )

    # Validate
    new_config.validate()

    # Store as runtime override
    _runtime_overrides = new_config

    return new_config


def reset_streaming_config() -> StreamingConfig:
    """
    Reset streaming configuration to environment variable defaults.

    Returns:
        Default StreamingConfig from environment variables
    """
    global _runtime_overrides
    _runtime_overrides = None
    return get_streaming_config()


# Convenience function for backward compatibility
def is_streaming_enabled() -> bool:
    """Check if sentence-level streaming is enabled globally."""
    return get_streaming_config().enabled
