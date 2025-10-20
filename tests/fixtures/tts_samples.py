"""
TTS sample data for testing

Provides sample Chatterbox TTS requests and responses
"""
from typing import Dict
from .audio_samples import get_sample_wav_audio


# ============================================================
# TTS Request Payloads
# ============================================================

def get_chatterbox_tts_request(
    text: str = "Hello from Chatterbox",
    voice: str = "default",
    speed: float = 1.0,
    response_format: str = "wav",
    streaming_strategy: str = "sentence",
    streaming_quality: str = "fast",
    chunk_size: int = 100
) -> Dict:
    """
    Get Chatterbox TTS request payload

    Args:
        text: Text to synthesize
        voice: Voice ID
        speed: Speed factor
        response_format: Output format
        streaming_strategy: Streaming strategy
        streaming_quality: Streaming quality
        chunk_size: Streaming chunk size

    Returns:
        Chatterbox TTS request dict
    """
    return {
        "input": text,
        "voice": voice,
        "speed": speed,
        "response_format": response_format,
        "streaming_strategy": streaming_strategy,
        "streaming_quality": streaming_quality,
        "streaming_chunk_size": chunk_size
    }


def get_chatterbox_tts_request_simple(text: str = "Test") -> Dict:
    """Get simple TTS request with minimal parameters"""
    return {
        "input": text,
        "voice": "default",
        "response_format": "wav",
        "speed": 1.0
    }


def get_chatterbox_tts_request_cloning(
    text: str = "Cloned voice test",
    reference_audio: str = "voice_sample.wav"
) -> Dict:
    """
    Get TTS request with voice cloning

    Args:
        text: Text to synthesize
        reference_audio: Reference audio filename

    Returns:
        TTS request with voice cloning
    """
    return {
        "input": text,
        "voice": reference_audio,
        "response_format": "wav",
        "speed": 1.0,
        "streaming_strategy": "sentence",
        "streaming_quality": "fast"
    }


def get_chatterbox_tts_request_advanced(
    text: str = "Advanced TTS test",
    temperature: float = 0.7,
    exaggeration: float = 0.5,
    cfg_weight: float = 3.0
) -> Dict:
    """
    Get TTS request with advanced generation parameters

    Args:
        text: Text to synthesize
        temperature: Generation temperature
        exaggeration: Exaggeration level
        cfg_weight: CFG weight

    Returns:
        Advanced TTS request
    """
    return {
        "input": text,
        "voice": "default",
        "response_format": "wav",
        "speed": 1.0,
        "temperature": temperature,
        "exaggeration": exaggeration,
        "cfg_weight": cfg_weight,
        "streaming_strategy": "sentence",
        "streaming_quality": "balanced",
        "streaming_chunk_size": 150
    }


# ============================================================
# TTS Response Data
# ============================================================

def get_sample_wav_audio() -> bytes:
    """
    Get sample WAV audio response

    Returns:
        WAV audio bytes
    """
    from .audio_samples import get_sample_wav_audio as _get_wav
    return _get_wav(duration_ms=2000, sample_rate=48000)


def get_streaming_wav_chunks(chunk_count: int = 10) -> list[bytes]:
    """
    Get streaming WAV audio chunks

    Args:
        chunk_count: Number of chunks to generate

    Returns:
        List of audio chunk bytes
    """
    # Generate a full WAV file
    full_audio = get_sample_wav_audio()

    # Split into chunks (skip WAV header for chunks after first)
    header_size = 44
    chunk_size = (len(full_audio) - header_size) // chunk_count

    chunks = []
    # First chunk includes WAV header
    chunks.append(full_audio[:header_size + chunk_size])

    # Remaining chunks are raw audio data
    for i in range(1, chunk_count):
        start = header_size + (i * chunk_size)
        end = start + chunk_size
        chunks.append(full_audio[start:end])

    return chunks


def get_empty_tts_response() -> bytes:
    """Get empty TTS response for error testing"""
    return b''


def get_corrupted_tts_response() -> bytes:
    """Get corrupted TTS response for error testing"""
    return b'\xFF\xFF\xFF\xFF' * 100


# ============================================================
# Chatterbox Error Responses
# ============================================================

def get_chatterbox_error_response(
    status_code: int = 500,
    error: str = "Internal server error"
) -> Dict:
    """
    Get Chatterbox error response

    Args:
        status_code: HTTP status code
        error: Error message

    Returns:
        Error response dict
    """
    return {
        "error": error,
        "status_code": status_code
    }


def get_chatterbox_validation_error() -> Dict:
    """Get validation error response"""
    return {
        "error": "Invalid input parameter",
        "status_code": 400,
        "detail": "Text input is required"
    }


# ============================================================
# TTS Options Templates
# ============================================================

def get_default_tts_options() -> Dict:
    """Get default TTS options"""
    return {
        "voiceMode": "default",
        "speedFactor": 1.0,
        "outputFormat": "wav",
        "streamingStrategy": "sentence",
        "streamingQuality": "fast",
        "chunkSize": 100
    }


def get_fast_tts_options() -> Dict:
    """Get TTS options optimized for low latency"""
    return {
        "voiceMode": "default",
        "speedFactor": 1.2,
        "outputFormat": "wav",
        "streamingStrategy": "word",
        "streamingQuality": "fast",
        "chunkSize": 50
    }


def get_quality_tts_options() -> Dict:
    """Get TTS options optimized for quality"""
    return {
        "voiceMode": "default",
        "speedFactor": 1.0,
        "outputFormat": "wav",
        "streamingStrategy": "paragraph",
        "streamingQuality": "high",
        "chunkSize": 200,
        "temperature": 0.7,
        "exaggeration": 0.3
    }


def get_cloning_tts_options(reference_audio: str = "voice.wav") -> Dict:
    """Get TTS options for voice cloning"""
    return {
        "voiceMode": "clone",
        "referenceAudioFilename": reference_audio,
        "speedFactor": 1.0,
        "outputFormat": "wav",
        "streamingStrategy": "sentence",
        "streamingQuality": "balanced",
        "chunkSize": 100
    }
