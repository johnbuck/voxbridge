"""
End-to-End tests for VoxBridge

Tests complete workflows:
- Join voice channel → Listen → Transcribe → AI Response → TTS → Leave
- Multi-user speaker management
- Error recovery and resilience
- Performance/latency validation

Run with: pytest tests/e2e/ -v
"""
