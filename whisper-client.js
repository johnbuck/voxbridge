// ============================================================
// Whisper Client
// WebSocket client for streaming audio to Faster Whisper server
// - Connects to local Whisper WebSocket server
// - Streams Opus audio chunks
// - Receives partial and final transcriptions
// ============================================================

const WebSocket = require('ws');

class WhisperClient {
  constructor() {
    this.ws = null;
    this.transcriptBuffer = '';
    this.isConnected = false;
    this.userId = null;
    this.resolveFinalize = null;
    
    // Configuration
    this.WHISPER_SERVER_URL = process.env.WHISPER_SERVER_URL || 'ws://localhost:4901';
  }

  /**
   * Connect to Whisper WebSocket server
   */
  connect(userId) {
    this.userId = userId;
    
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.WHISPER_SERVER_URL);

        this.ws.on('open', () => {
          console.log(`🔌 Whisper WebSocket connected for user ${userId}`);
          this.isConnected = true;
          
          // Send initial metadata
          this.ws.send(JSON.stringify({
            type: 'start',
            userId: userId,
            language: process.env.WHISPER_LANGUAGE || 'en'
          }));
          
          resolve();
        });

        this.ws.on('message', (data) => {
          this.handleMessage(data);
        });

        this.ws.on('error', (error) => {
          console.error(`❌ Whisper WebSocket error for ${userId}:`, error.message);
          reject(error);
        });

        this.ws.on('close', () => {
          console.log(`🔌 Whisper WebSocket closed for user ${userId}`);
          this.isConnected = false;
        });

      } catch (error) {
        console.error(`❌ Failed to connect to Whisper server:`, error.message);
        reject(error);
      }
    });
  }

  /**
   * Handle incoming messages from Whisper server
   */
  handleMessage(data) {
    try {
      const message = JSON.parse(data.toString());

      switch (message.type) {
        case 'partial':
          // Partial transcription result (real-time)
          if (message.text) {
            console.log(`🔄 Partial: "${message.text}"`);
            this.transcriptBuffer = message.text;
          }
          break;

        case 'final':
          // Final transcription result
          if (message.text) {
            console.log(`✅ Final: "${message.text}"`);
            this.transcriptBuffer = message.text;
          }
          
          // Resolve pending finalize promise
          if (this.resolveFinalize) {
            this.resolveFinalize(this.transcriptBuffer);
            this.resolveFinalize = null;
          }
          break;

        case 'error':
          console.error(`❌ Whisper error: ${message.error}`);
          
          // Resolve pending finalize with empty string on error
          if (this.resolveFinalize) {
            this.resolveFinalize('');
            this.resolveFinalize = null;
          }
          break;

        default:
          console.log(`ℹ️ Unknown message type: ${message.type}`);
      }

    } catch (error) {
      console.error('❌ Error parsing Whisper message:', error.message);
    }
  }

  /**
   * Send audio chunk to Whisper server
   */
  sendAudio(opusChunk) {
    if (!this.isConnected || !this.ws) {
      console.warn('⚠️ Cannot send audio - WebSocket not connected');
      return;
    }

    try {
      // Send raw Opus audio data
      this.ws.send(opusChunk);
    } catch (error) {
      console.error('❌ Error sending audio to Whisper:', error.message);
    }
  }

  /**
   * Finalize transcription and get result
   * Returns a promise that resolves with the final transcript
   */
  finalize() {
    return new Promise((resolve, reject) => {
      if (!this.isConnected || !this.ws) {
        resolve(this.transcriptBuffer);
        return;
      }

      // Store resolve function to call when we get final result
      this.resolveFinalize = resolve;

      // Send finalize signal to Whisper server
      try {
        this.ws.send(JSON.stringify({
          type: 'finalize'
        }));

        // Set timeout in case we don't get a response
        setTimeout(() => {
          if (this.resolveFinalize) {
            console.log('⏱️ Finalize timeout - returning buffered transcript');
            resolve(this.transcriptBuffer);
            this.resolveFinalize = null;
          }
        }, 2000);

      } catch (error) {
        console.error('❌ Error finalizing transcription:', error.message);
        resolve(this.transcriptBuffer);
      }
    });
  }

  /**
   * Close WebSocket connection
   */
  close() {
    if (this.ws) {
      try {
        // Send close signal
        if (this.isConnected) {
          this.ws.send(JSON.stringify({
            type: 'close'
          }));
        }
        
        this.ws.close();
      } catch (error) {
        console.error('❌ Error closing Whisper WebSocket:', error.message);
      }
      
      this.ws = null;
      this.isConnected = false;
    }

    // Resolve any pending finalize
    if (this.resolveFinalize) {
      this.resolveFinalize(this.transcriptBuffer);
      this.resolveFinalize = null;
    }
  }

  /**
   * Get current transcript buffer
   */
  getTranscript() {
    return this.transcriptBuffer;
  }
}

module.exports = WhisperClient;
