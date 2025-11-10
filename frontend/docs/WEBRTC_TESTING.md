# WebRTC Audio Capture - Testing Guide

This document provides instructions for testing the WebRTC audio capture feature without a backend server.

## Overview

The WebRTC audio capture feature consists of three main components:

1. **useWebRTCAudio.ts** - Custom React hook for microphone access and WebSocket streaming
2. **AudioControls.tsx** - UI component with mute/unmute button and connection status
3. **VoiceChatPage.tsx** - Integration with conversation UI and message handling

## Testing Without Backend

You can test the frontend WebRTC implementation using a mock WebSocket server. Below are two options:

### Option 1: Browser Console Mock

You can simulate WebSocket messages directly in the browser console for basic testing:

```javascript
// In browser console (after unmuting microphone):
// This won't work perfectly because the WebSocket is internal to the hook,
// but you can verify the UI handles messages correctly by using the React DevTools
```

### Option 2: Node.js Mock WebSocket Server

Create a simple WebSocket server for testing:

**File: `mock-voice-server.js`**

```javascript
const WebSocket = require('ws');

const wss = new WebSocket.Server({ port: 4900 });

console.log('Mock WebSocket server listening on ws://localhost:4900');

wss.on('connection', (ws) => {
  console.log('[WebSocket] Client connected');

  ws.on('message', (message) => {
    // Check if it's binary (audio data) or JSON
    if (message instanceof Buffer) {
      console.log(`[WebSocket] Received audio chunk: ${message.length} bytes`);

      // Simulate partial transcript after 500ms
      setTimeout(() => {
        ws.send(JSON.stringify({
          event: 'partial_transcript',
          data: {
            text: 'This is a partial transcript...',
            session_id: 'test-session-id',
          },
        }));
      }, 500);

      // Simulate final transcript after 2s
      setTimeout(() => {
        ws.send(JSON.stringify({
          event: 'final_transcript',
          data: {
            text: 'This is the final transcript of what you said.',
            session_id: 'test-session-id',
          },
        }));
      }, 2000);

      // Simulate AI response chunks
      setTimeout(() => {
        const chunks = [
          'Hello! ',
          'I heard you say: ',
          '"This is the final transcript of what you said." ',
          'How can I help you today?',
        ];

        chunks.forEach((chunk, index) => {
          setTimeout(() => {
            ws.send(JSON.stringify({
              event: 'ai_response_chunk',
              data: {
                text: chunk,
                session_id: 'test-session-id',
              },
            }));

            // Send complete event after last chunk
            if (index === chunks.length - 1) {
              setTimeout(() => {
                ws.send(JSON.stringify({
                  event: 'ai_response_complete',
                  data: {
                    text: chunks.join(''),
                    session_id: 'test-session-id',
                  },
                }));
              }, 100);
            }
          }, index * 200);
        });
      }, 3000);
    } else {
      // JSON message (session init, etc.)
      try {
        const data = JSON.parse(message.toString());
        console.log('[WebSocket] Received JSON:', data);
      } catch (err) {
        console.error('[WebSocket] Failed to parse JSON:', err);
      }
    }
  });

  ws.on('close', () => {
    console.log('[WebSocket] Client disconnected');
  });

  ws.on('error', (error) => {
    console.error('[WebSocket] Error:', error);
  });
});
```

**Run the mock server:**

```bash
# Install ws package
npm install ws

# Run the server
node mock-voice-server.js
```

**Update frontend to use mock server:**

```bash
# In frontend directory
export VITE_WS_URL=ws://localhost:4900
npm run dev
```

## WebSocket Protocol

### Client → Server (Audio Chunks)

- **Type**: Binary (ArrayBuffer)
- **Format**: Opus or WebM/Opus audio data
- **Frequency**: Every 100ms (configurable via `timeslice` parameter)

### Server → Client (Events)

All messages are JSON with this structure:

```typescript
{
  event: 'partial_transcript' | 'final_transcript' | 'ai_response_chunk' | 'ai_response_complete',
  data: {
    text: string,
    user_id?: string,
    session_id?: string,
  }
}
```

#### Event Types

1. **partial_transcript** - Live transcription as user speaks
   - Displayed in real-time in a faded message bubble
   - Updates continuously until final transcript

2. **final_transcript** - Complete user message
   - Replaces partial transcript
   - Saved to database via API
   - Triggers AI response

3. **ai_response_chunk** - Streaming AI response
   - Appended to assistant message in real-time
   - Creates smooth streaming UX

4. **ai_response_complete** - Final AI response
   - Saved to database via API
   - Includes full message text

## Testing Checklist

### Microphone Access
- [ ] Browser requests microphone permission on first unmute
- [ ] Permission denied shows error toast with instructions
- [ ] No microphone device shows appropriate error
- [ ] Microphone indicator turns red when unmuted
- [ ] Pulse animation shows when actively recording

### WebSocket Connection
- [ ] Connection status badge shows "Connecting..." initially
- [ ] Badge turns green with "Connected" when WebSocket opens
- [ ] Badge shows "Disconnected" when WebSocket closes
- [ ] Auto-reconnect attempts on disconnect (max 5 times)
- [ ] Buffered audio discarded on reconnect

### Audio Streaming
- [ ] Audio chunks sent every 100ms when unmuted
- [ ] Browser console shows "Recording started" message
- [ ] WebSocket sends binary data (check Network tab)
- [ ] No audio sent when muted
- [ ] Recording stops cleanly when muted

### Transcription Display
- [ ] Partial transcripts appear in faded message bubble
- [ ] "(speaking...)" indicator shows next to username
- [ ] Partial transcript updates in real-time
- [ ] Final transcript replaces partial transcript
- [ ] Final transcript saved to database (check Network tab)

### AI Response Streaming
- [ ] AI response chunks append to last message
- [ ] Smooth streaming animation (no flickering)
- [ ] Complete response saved to database
- [ ] Messages refetched after save (proper ID from backend)

### Error Handling
- [ ] Toast notification on permission error
- [ ] Toast notification on WebSocket error
- [ ] Reconnection attempts logged in console
- [ ] Audio recording errors handled gracefully

### UI/UX
- [ ] Mute/unmute button toggles correctly
- [ ] Connection status badge updates in real-time
- [ ] Scroll area scrolls to bottom on new messages
- [ ] Message timestamps formatted correctly
- [ ] Speaker name shows correctly (You vs Agent name)

## Browser Compatibility

### Supported Browsers
- **Chrome/Edge**: Full support (Opus codec)
- **Firefox**: Full support (Opus codec)
- **Safari**: Partial support (may need WebM fallback)

### Required Features
- `navigator.mediaDevices.getUserMedia()` - Microphone access
- `MediaRecorder` API - Audio encoding
- `WebSocket` API - Binary data streaming
- Opus codec support (or WebM/Opus fallback)

## Debugging Tips

### Enable Verbose Logging

All console logs are prefixed with `[WebRTC]` for easy filtering:

```javascript
// In browser console, filter logs:
// Chrome DevTools → Console → Filter: "[WebRTC]"
```

### Check WebSocket Traffic

1. Open Chrome DevTools → Network tab
2. Filter by "WS" (WebSocket)
3. Click on `/ws/voice` connection
4. View messages and binary frames

### Verify Audio Codec

```javascript
// In browser console:
console.log(MediaRecorder.isTypeSupported('audio/webm;codecs=opus')); // Should be true
console.log(MediaRecorder.isTypeSupported('audio/ogg;codecs=opus'));  // Fallback
```

### Monitor MediaRecorder State

The `isRecording` state should match the MediaRecorder state:
- `true` when `mediaRecorder.state === 'recording'`
- `false` when `mediaRecorder.state === 'inactive'`

## Common Issues

### Issue: Microphone permission denied

**Solution**:
1. Check browser permissions (chrome://settings/content/microphone)
2. Ensure HTTPS or localhost (required for getUserMedia)
3. Reload page after granting permission

### Issue: No audio chunks sent

**Solution**:
1. Check `mediaRecorder.state` in React DevTools
2. Verify WebSocket connection is open
3. Check console for MediaRecorder errors
4. Ensure timeslice is set (100ms)

### Issue: WebSocket disconnects immediately

**Solution**:
1. Verify backend WebSocket endpoint exists (`/ws/voice`)
2. Check CORS settings (if frontend/backend on different domains)
3. Check backend WebSocket handler accepts binary data

### Issue: Streaming responses don't update

**Solution**:
1. Verify `queryClient.setQueryData()` is called
2. Check React Query DevTools for cache updates
3. Ensure `activeSessionId` is set correctly

## Integration with Backend

Once the backend implements the `/ws/voice` endpoint, ensure:

1. **Audio Processing**: Backend should decode Opus audio chunks
2. **WhisperX Integration**: Forward audio to WhisperX for transcription
3. **LLM Integration**: Send final transcript to LLM for response
4. **TTS Integration**: Generate audio response (if applicable)
5. **Session Management**: Associate messages with correct session ID

See `docs/architecture/voxbridge-2.0-transformation-plan.md` for full Phase 4 backend requirements.
