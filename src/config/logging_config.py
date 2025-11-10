"""
Tiered Logging Configuration for VoxBridge

Provides a flexible logging system with 5 levels:
- TRACE (5): Ultra-verbose debugging (raw data, every iteration)
- DEBUG (10): Detailed debugging (checkpoints, state changes)
- INFO (20): Standard operational messages (connections, completions)
- WARN (30): Warnings (recoverable errors, fallbacks)
- ERROR (40): Errors (exceptions, failures)

Environment Variables:
- LOG_LEVEL: Global log level (TRACE, DEBUG, INFO, WARN, ERROR) [default: INFO]
- LOG_LEVEL_VOICE: Override for voice module (webrtc_handler, audio processing)
- LOG_LEVEL_STT: Override for STT service (WhisperX, transcription)
- LOG_LEVEL_LLM: Override for LLM service (OpenRouter, local LLM)
- LOG_LEVEL_TTS: Override for TTS service (Chatterbox, synthesis)
- LOG_LEVEL_CONVERSATION: Override for conversation service (session management)
- LOG_LEVEL_DISCORD: Override for Discord plugin (bot, voice channel)
- LOG_LEVEL_WEBRTC: Override for WebRTC handler (browser voice chat)

Example Usage:
    from src.config.logging_config import get_logger

    logger = get_logger(__name__)
    logger.trace("🔍 Raw audio chunk: %d bytes", len(chunk))
    logger.debug("🎙️ Checkpoint: finalized transcript")
    logger.info("✅ Connected to WhisperX server")
    logger.warning("⚠️ Retrying connection (attempt 2/3)")
    logger.error("❌ Failed to decode audio: %s", error)
"""

import logging
import os
from typing import Dict, Optional


# Define custom TRACE level (more verbose than DEBUG)
TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def trace(self, message, *args, **kwargs):
    """Log a message with severity 'TRACE'."""
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)


# Add trace method to Logger class
logging.Logger.trace = trace


# Module name mapping: Python module path → Logical service name
MODULE_NAME_MAP = {
    "src.voice.webrtc_handler": "voxbridge.voice",
    "src.services.stt_service": "voxbridge.stt",
    "src.services.llm_service": "voxbridge.llm",
    "src.services.tts_service": "voxbridge.tts",
    "src.services.conversation_service": "voxbridge.conversation",
    "src.plugins.discord_plugin": "voxbridge.discord",
    "src.discord_bot": "voxbridge.discord",
    "src.whisper_server": "voxbridge.whisperx",
}


def get_log_level(module_name: str, default: str = "INFO") -> int:
    """
    Get the log level for a module, checking both module-specific and global env vars.

    Priority:
    1. Module-specific env var (LOG_LEVEL_VOICE, LOG_LEVEL_STT, etc.)
    2. Global LOG_LEVEL env var
    3. Default level (INFO)

    Args:
        module_name: Python module name (e.g., "src.voice.webrtc_handler")
        default: Default log level if no env vars set

    Returns:
        Numeric log level (5=TRACE, 10=DEBUG, 20=INFO, 30=WARN, 40=ERROR)
    """
    # Map module name to logical service name
    logical_name = MODULE_NAME_MAP.get(module_name, module_name)

    # Extract service name from logical name (e.g., "voxbridge.voice" → "VOICE")
    if "." in logical_name:
        service_name = logical_name.split(".")[-1].upper()
    else:
        service_name = None

    # Check module-specific env var first
    if service_name:
        module_level = os.getenv(f"LOG_LEVEL_{service_name}")
        if module_level:
            return _parse_log_level(module_level)

    # Check global LOG_LEVEL env var
    global_level = os.getenv("LOG_LEVEL")
    if global_level:
        return _parse_log_level(global_level)

    # Use default
    return _parse_log_level(default)


def _parse_log_level(level_str: str) -> int:
    """
    Parse log level string to numeric value.

    Args:
        level_str: Log level name (TRACE, DEBUG, INFO, WARN, ERROR)

    Returns:
        Numeric log level
    """
    level_map = {
        "TRACE": TRACE,
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    return level_map.get(level_str.upper(), logging.INFO)


def configure_logging(default_level: str = "INFO") -> None:
    """
    Configure logging system with tiered levels and per-module control.

    This should be called once at application startup (e.g., in discord_bot.py).

    Args:
        default_level: Default log level if LOG_LEVEL env var not set
    """
    # Get global log level
    global_level = os.getenv("LOG_LEVEL", default_level)
    numeric_level = _parse_log_level(global_level)

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    # Log initialization message
    root_logger = logging.getLogger()
    root_logger.info(f"🚀 Logging system initialized (global level: {global_level})")

    # Log per-module overrides if any
    module_overrides = []
    for env_var in ["VOICE", "STT", "LLM", "TTS", "CONVERSATION", "DISCORD", "WEBRTC"]:
        override = os.getenv(f"LOG_LEVEL_{env_var}")
        if override:
            module_overrides.append(f"{env_var}={override}")

    if module_overrides:
        root_logger.info(f"📋 Module overrides: {', '.join(module_overrides)}")


def get_logger(module_name: str) -> logging.Logger:
    """
    Get a logger for a module with appropriate log level.

    This is the main entry point for getting loggers in VoxBridge code.

    Args:
        module_name: Python module name (use __name__)

    Returns:
        Configured logger instance

    Example:
        logger = get_logger(__name__)
        logger.trace("🔍 Raw data: %s", data)
        logger.debug("🎙️ Checkpoint reached")
        logger.info("✅ Operation complete")
    """
    logger = logging.getLogger(module_name)

    # Set module-specific log level if configured
    level = get_log_level(module_name)
    logger.setLevel(level)

    return logger


# Convenience function for quick testing
def test_logging():
    """Test the logging configuration with all levels."""
    configure_logging("TRACE")

    logger = get_logger(__name__)
    logger.trace("🔍 TRACE: Ultra-verbose debugging")
    logger.debug("🐛 DEBUG: Detailed debugging")
    logger.info("ℹ️ INFO: Standard operational message")
    logger.warning("⚠️ WARN: Warning message")
    logger.error("❌ ERROR: Error message")


if __name__ == "__main__":
    test_logging()
