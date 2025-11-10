#!/usr/bin/env node
/**
 * Mock WebSocket Server for WebRTC Audio Testing
 * VoxBridge 2.0 Phase 4: Web Voice Interface
 *
 * Usage:
 *   npm install ws
 *   node mock-voice-server.js
 *
 * Then set VITE_WS_URL=ws://localhost:4900 and start frontend
 */

const WebSocket = require('ws');

const PORT = 4900;
const wss = new WebSocket.Server({ port: PORT });

console.log('╔════════════════════════════════════════════════════════════╗');
console.log('║   Mock WebSocket Server for VoxBridge WebRTC Testing      ║');
console.log('╚════════════════════════════════════════════════════════════╝');
console.log('');
console.log(`✅ Server listening on ws://localhost:${PORT}`);
console.log('');
console.log('Endpoints:');
console.log('  • /ws/voice - WebRTC audio streaming');
console.log('');
console.log('Waiting for connections...');
console.log('');

wss.on('connection', (ws, req) => {
  const endpoint = req.url;
  console.log(`[WebSocket] 🔌 Client connected to ${endpoint}`);

  let audioChunkCount = 0;
  let sessionId = null;

  ws.on('message', (message) => {
    // Check if it's binary (audio data) or JSON
    if (message instanceof Buffer) {
      audioChunkCount++;
      console.log(`[Audio] 🎤 Received audio chunk #${audioChunkCount}: ${message.length} bytes`);

      // Simulate partial transcript after first chunk
      if (audioChunkCount === 1) {
        setTimeout(() => {
          const partialMessage = {
            event: 'partial_transcript',
            data: {
              text: 'Hello',
              session_id: sessionId,
            },
          };
          ws.send(JSON.stringify(partialMessage));
          console.log('[Response] 📝 Sent partial transcript: "Hello"');
        }, 500);
      }

      // Simulate more partial transcripts
      if (audioChunkCount === 5) {
        setTimeout(() => {
          const partialMessage = {
            event: 'partial_transcript',
            data: {
              text: 'Hello, I am testing',
              session_id: sessionId,
            },
          };
          ws.send(JSON.stringify(partialMessage));
          console.log('[Response] 📝 Sent partial transcript: "Hello, I am testing"');
        }, 100);
      }

      if (audioChunkCount === 10) {
        setTimeout(() => {
          const partialMessage = {
            event: 'partial_transcript',
            data: {
              text: 'Hello, I am testing the voice capture',
              session_id: sessionId,
            },
          };
          ws.send(JSON.stringify(partialMessage));
          console.log('[Response] 📝 Sent partial transcript: "Hello, I am testing the voice capture"');
        }, 100);
      }

      // Simulate final transcript after 15 chunks (~1.5 seconds of audio)
      if (audioChunkCount === 15) {
        setTimeout(() => {
          const finalMessage = {
            event: 'final_transcript',
            data: {
              text: 'Hello, I am testing the voice capture feature.',
              session_id: sessionId,
            },
          };
          ws.send(JSON.stringify(finalMessage));
          console.log('[Response] ✅ Sent final transcript: "Hello, I am testing the voice capture feature."');

          // Simulate AI response chunks
          setTimeout(() => {
            const aiChunks = [
              'Hi there! ',
              'I heard you say: ',
              '"Hello, I am testing the voice capture feature." ',
              'That\'s great! ',
              'The WebRTC audio capture is working perfectly. ',
              'How can I help you today?',
            ];

            aiChunks.forEach((chunk, index) => {
              setTimeout(() => {
                const chunkMessage = {
                  event: 'ai_response_chunk',
                  data: {
                    text: chunk,
                    session_id: sessionId,
                  },
                };
                ws.send(JSON.stringify(chunkMessage));
                console.log(`[Response] 💬 Sent AI chunk ${index + 1}/${aiChunks.length}: "${chunk.trim()}"`);

                // Send complete event after last chunk
                if (index === aiChunks.length - 1) {
                  setTimeout(() => {
                    const completeMessage = {
                      event: 'ai_response_complete',
                      data: {
                        text: aiChunks.join(''),
                        session_id: sessionId,
                      },
                    };
                    ws.send(JSON.stringify(completeMessage));
                    console.log('[Response] 🎉 Sent AI response complete');
                    console.log('');
                    console.log('Ready for next utterance...');
                    console.log('');

                    // Reset chunk count for next utterance
                    audioChunkCount = 0;
                  }, 200);
                }
              }, index * 200); // Stagger chunks 200ms apart
            });
          }, 500); // Wait 500ms before starting AI response
        }, 200); // Wait 200ms before sending final transcript
      }
    } else {
      // JSON message (session init, etc.)
      try {
        const data = JSON.parse(message.toString());
        console.log('[JSON] 📨 Received:', data);

        if (data.event === 'session_init') {
          sessionId = data.session_id;
          console.log(`[Session] 🎯 Session ID: ${sessionId}`);
        }
      } catch (err) {
        console.error('[Error] ❌ Failed to parse JSON:', err.message);
      }
    }
  });

  ws.on('close', () => {
    console.log('[WebSocket] 🔌 Client disconnected');
    console.log('');
    console.log('Waiting for connections...');
    console.log('');
  });

  ws.on('error', (error) => {
    console.error('[Error] ❌ WebSocket error:', error.message);
  });
});

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('');
  console.log('[Server] 🛑 Shutting down...');
  wss.close(() => {
    console.log('[Server] ✅ Server closed');
    process.exit(0);
  });
});

process.on('SIGTERM', () => {
  console.log('');
  console.log('[Server] 🛑 Shutting down...');
  wss.close(() => {
    console.log('[Server] ✅ Server closed');
    process.exit(0);
  });
});
