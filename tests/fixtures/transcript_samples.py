"""
Transcript sample data for testing

Provides sample transcripts, WhisperX responses, and n8n payloads
"""
from typing import List, Dict


# ============================================================
# Sample Transcripts
# ============================================================

SAMPLE_TRANSCRIPTS = [
    "Hello, this is a test of the VoxBridge speech to text system.",
    "The quick brown fox jumps over the lazy dog.",
    "Testing one two three, can you hear me?",
    "What is the weather like today?",
    "Please tell me a joke about programming.",
    "How do I deploy a Docker container?",
    "What time is it in Tokyo right now?",
]


def get_sample_transcript(index: int = 0) -> str:
    """Get a sample transcript by index"""
    return SAMPLE_TRANSCRIPTS[index % len(SAMPLE_TRANSCRIPTS)]


def get_random_transcript() -> str:
    """Get a random transcript"""
    import random
    return random.choice(SAMPLE_TRANSCRIPTS)


def get_long_transcript() -> str:
    """Get a longer transcript for testing max speaking time"""
    return " ".join(SAMPLE_TRANSCRIPTS * 5)


def get_empty_transcript() -> str:
    """Get empty transcript for edge case testing"""
    return ""


def get_special_characters_transcript() -> str:
    """Get transcript with special characters"""
    return "Hello! How are you? I'm testing... #VoxBridge @mentions $100 & more!"


# ============================================================
# WhisperX WebSocket Messages
# ============================================================

def get_whisperx_partial_message(text: str = None) -> dict:
    """
    Get WhisperX partial transcription message

    Args:
        text: Partial transcript text (uses default if None)

    Returns:
        WhisperX partial message dict
    """
    return {
        "type": "partial",
        "text": text or "Hello this is"
    }


def get_whisperx_final_message(text: str = None) -> dict:
    """
    Get WhisperX final transcription message

    Args:
        text: Final transcript text (uses default if None)

    Returns:
        WhisperX final message dict
    """
    return {
        "type": "final",
        "text": text or "Hello this is a test."
    }


def get_whisperx_error_message(error: str = "Connection lost") -> dict:
    """
    Get WhisperX error message

    Args:
        error: Error message text

    Returns:
        WhisperX error message dict
    """
    return {
        "type": "error",
        "error": error
    }


def get_whisperx_start_message(user_id: str = "123456789", language: str = "en") -> dict:
    """
    Get WhisperX start message (sent by client)

    Args:
        user_id: Discord user ID
        language: Language code

    Returns:
        WhisperX start message dict
    """
    return {
        "type": "start",
        "userId": user_id,
        "language": language
    }


def get_whisperx_finalize_message() -> dict:
    """Get WhisperX finalize message (sent by client)"""
    return {
        "type": "finalize"
    }


# ============================================================
# n8n Webhook Payloads
# ============================================================

def get_n8n_webhook_payload(
    text: str = None,
    user_id: str = "123456789",
    use_streaming: bool = True
) -> dict:
    """
    Get n8n webhook POST payload

    Args:
        text: Transcript text
        user_id: Discord user ID
        use_streaming: Enable streaming response

    Returns:
        n8n webhook payload dict
    """
    from datetime import datetime

    return {
        "text": text or get_sample_transcript(),
        "userId": user_id,
        "timestamp": datetime.now().isoformat(),
        "useStreaming": use_streaming
    }


def get_n8n_response_simple(transcript: str = None) -> dict:
    """
    Get simple n8n response (non-streaming)

    Args:
        transcript: Original transcript

    Returns:
        n8n response dict
    """
    transcript = transcript or get_sample_transcript()
    return {
        "output": {
            "content": f"Echo: {transcript}"
        },
        "options": {
            "voiceMode": "default",
            "speedFactor": 1.0,
            "outputFormat": "wav"
        }
    }


def get_n8n_response_with_options(
    content: str = "Test response",
    voice_mode: str = "default",
    speed: float = 1.0,
    streaming_strategy: str = "sentence",
    streaming_quality: str = "fast",
    chunk_size: int = 100
) -> dict:
    """
    Get n8n response with full TTS options

    Args:
        content: Response text
        voice_mode: Voice mode (default, clone)
        speed: Speed factor
        streaming_strategy: Streaming strategy
        streaming_quality: Streaming quality
        chunk_size: Streaming chunk size

    Returns:
        n8n response with options
    """
    return {
        "output": {
            "content": content
        },
        "options": {
            "voiceMode": voice_mode,
            "speedFactor": speed,
            "outputFormat": "wav",
            "streamingStrategy": streaming_strategy,
            "streamingQuality": streaming_quality,
            "chunkSize": chunk_size
        }
    }


def get_n8n_streaming_chunks(text: str = None) -> List[str]:
    """
    Get n8n SSE streaming chunks

    Args:
        text: Text to split into chunks (uses default if None)

    Returns:
        List of SSE data chunks
    """
    text = text or "Hello from n8n! This is a streaming response."
    words = text.split()

    chunks = []
    for word in words:
        chunks.append(f"data: {word} \n\n")

    chunks.append("data: [DONE]\n\n")

    return chunks


def get_n8n_streaming_response_full(text: str = None) -> str:
    """
    Get full SSE streaming response as string

    Args:
        text: Text to stream

    Returns:
        Complete SSE response string
    """
    chunks = get_n8n_streaming_chunks(text)
    return "".join(chunks)
