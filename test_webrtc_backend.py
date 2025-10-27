#!/usr/bin/env python3
"""
WebRTC Backend Test Script

Quick integration test for /ws/voice endpoint.
Tests connection, audio streaming, and event reception.

Usage:
    python test_webrtc_backend.py SESSION_UUID USER_ID

Example:
    python test_webrtc_backend.py 12345678-1234-1234-1234-123456789abc test-user-123
"""

import asyncio
import sys
import json
from typing import Optional

try:
    import websockets
    import opuslib
except ImportError:
    print("❌ Missing dependencies. Install with:")
    print("   pip install websockets opuslib")
    sys.exit(1)


class WebRTCTester:
    """Test client for /ws/voice endpoint"""

    def __init__(self, session_id: str, user_id: str, host: str = "localhost", port: int = 4900):
        self.session_id = session_id
        self.user_id = user_id
        self.uri = f"ws://{host}:{port}/ws/voice?session_id={session_id}&user_id={user_id}"
        self.encoder = opuslib.Encoder(16000, 1, opuslib.APPLICATION_VOIP)
        self.events_received = []

    async def test_connection(self):
        """Test 1: WebSocket connection"""
        print("\n🧪 Test 1: WebSocket Connection")
        print(f"   Connecting to: {self.uri}")

        try:
            async with websockets.connect(self.uri) as ws:
                print("   ✅ Connection successful")
                return True
        except Exception as e:
            print(f"   ❌ Connection failed: {e}")
            return False

    async def test_audio_streaming(self):
        """Test 2: Send audio and receive events"""
        print("\n🧪 Test 2: Audio Streaming and Event Reception")

        try:
            async with websockets.connect(self.uri) as ws:
                print("   ✅ Connected")

                # Create silent PCM audio (16kHz mono, 20ms frames = 320 samples)
                import array
                silent_pcm = array.array('h', [0] * 320).tobytes()

                # Send 50 frames (1 second of silent audio)
                print("   🎙️ Sending 50 audio frames (1 second of silence)...")
                for i in range(50):
                    opus_data = self.encoder.encode(silent_pcm, 320)
                    await ws.send(opus_data)
                    await asyncio.sleep(0.02)  # 20ms per frame

                print("   ✅ Audio sent successfully")
                print("   ⏸️ Waiting for silence detection (600ms)...")
                await asyncio.sleep(1.0)

                # Receive events
                print("   📨 Receiving server events...")
                timeout_count = 0
                while timeout_count < 3:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        event = json.loads(message)
                        self.events_received.append(event)
                        event_type = event.get('event', 'unknown')
                        event_data = event.get('data', {})

                        if event_type == 'partial_transcript':
                            print(f"   📝 Partial: \"{event_data.get('text', '')}\"")
                        elif event_type == 'final_transcript':
                            print(f"   ✅ Final: \"{event_data.get('text', '')}\"")
                        elif event_type == 'ai_response_chunk':
                            print(f"   🤖 AI Chunk: \"{event_data.get('text', '')}\"")
                        elif event_type == 'ai_response_complete':
                            print(f"   ✅ AI Complete: \"{event_data.get('text', '')}\"")
                        elif event_type == 'error':
                            print(f"   ❌ Error: {event_data.get('message', '')}")
                        else:
                            print(f"   📨 Event: {event_type}")

                        timeout_count = 0  # Reset timeout counter on successful receive

                    except asyncio.TimeoutError:
                        timeout_count += 1
                        if timeout_count == 1:
                            print("   ⏱️ Waiting for more events...")

                print(f"   ✅ Received {len(self.events_received)} events")
                return True

        except Exception as e:
            print(f"   ❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def test_error_handling(self):
        """Test 3: Error handling with invalid session"""
        print("\n🧪 Test 3: Error Handling (Invalid Session)")

        invalid_uri = f"ws://localhost:4900/ws/voice?session_id=invalid-uuid&user_id=test"
        print(f"   Connecting with invalid session ID...")

        try:
            async with websockets.connect(invalid_uri) as ws:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    event = json.loads(message)
                    if event.get('event') == 'error':
                        print(f"   ✅ Error event received: {event['data']['message']}")
                        return True
                    else:
                        print(f"   ❌ Expected error event, got: {event}")
                        return False
                except asyncio.TimeoutError:
                    print("   ❌ No error event received")
                    return False
        except Exception as e:
            print(f"   ❌ Test failed: {e}")
            return False

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📊 Test Summary")
        print("=" * 60)
        print(f"Total events received: {len(self.events_received)}")

        event_types = {}
        for event in self.events_received:
            event_type = event.get('event', 'unknown')
            event_types[event_type] = event_types.get(event_type, 0) + 1

        for event_type, count in event_types.items():
            print(f"  - {event_type}: {count}")

        print("=" * 60)

    async def run_all_tests(self):
        """Run all tests"""
        print("=" * 60)
        print("🚀 VoxBridge WebRTC Backend Test Suite")
        print("=" * 60)
        print(f"Session ID: {self.session_id}")
        print(f"User ID: {self.user_id}")

        results = []

        # Test 1: Connection
        results.append(await self.test_connection())

        # Test 2: Audio streaming
        results.append(await self.test_audio_streaming())

        # Test 3: Error handling
        results.append(await self.test_error_handling())

        # Summary
        self.print_summary()

        # Final result
        passed = sum(results)
        total = len(results)
        print(f"\n{'✅' if passed == total else '❌'} Tests passed: {passed}/{total}")

        if passed == total:
            print("\n🎉 All tests passed! Backend is working correctly.")
        else:
            print("\n⚠️ Some tests failed. Check logs for details.")

        return passed == total


async def main():
    """Main entry point"""
    if len(sys.argv) < 3:
        print("Usage: python test_webrtc_backend.py SESSION_UUID USER_ID")
        print("\nExample:")
        print("  python test_webrtc_backend.py 12345678-1234-1234-1234-123456789abc test-user-123")
        print("\nNote: Create a session first using:")
        print("  curl -X POST http://localhost:4900/api/sessions -H 'Content-Type: application/json' \\")
        print("    -d '{\"user_id\":\"test-user-123\",\"agent_id\":\"AGENT_UUID\",\"title\":\"Test\"}'")
        sys.exit(1)

    session_id = sys.argv[1]
    user_id = sys.argv[2]

    tester = WebRTCTester(session_id, user_id)
    success = await tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Test interrupted by user")
        sys.exit(1)
