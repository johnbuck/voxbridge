// ============================================================
// Speaker Manager
// Handles single-speaker lock for voice transcription
// - Only one speaker can be transcribed at a time
// - Other speakers are ignored until current speaker finishes
// - Automatic timeout after 45 seconds
// - Silence detection (800ms) to finalize transcription
// ============================================================

const WhisperClient = require('./whisper-client');
const StreamingResponseHandler = require('./streaming-response-handler');
const axios = require('axios');

class SpeakerManager {
  constructor() {
    this.activeSpeaker = null;
    this.lockStartTime = null;
    this.whisperClient = null;
    this.timeoutTimer = null;
    this.silenceTimer = null;
    this.lastAudioTime = null;
    this.voiceConnection = null;
    this.streamingHandler = null;
    
    // Configuration
    this.SILENCE_THRESHOLD_MS = parseInt(process.env.SILENCE_THRESHOLD_MS) || 800;
    this.MAX_SPEAKING_TIME_MS = parseInt(process.env.MAX_SPEAKING_TIME_MS) || 45000;
    this.N8N_WEBHOOK_URL = process.env.N8N_WEBHOOK_URL;
    this.USE_STREAMING = process.env.USE_STREAMING !== 'false'; // Enable by default
  }

  /**
   * Handle user starting to speak
   * Returns true if this speaker is now active, false if ignored
   */
  onSpeakingStart(userId, opusStream) {
    // Someone already talking? Ignore this speaker.
    if (this.activeSpeaker) {
      console.log(`🔇 Ignoring ${userId} - ${this.activeSpeaker} is currently speaking`);
      return false;
    }

    // Lock to this speaker
    this.activeSpeaker = userId;
    this.lockStartTime = Date.now();
    this.lastAudioTime = Date.now();
    
    console.log(`🎤 ${userId} is now speaking (locked)`);
    
    // Start Whisper transcription stream
    this.startTranscription(userId, opusStream);
    
    // Set timeout timer (45 seconds max)
    this.timeoutTimer = setTimeout(() => {
      console.log(`⏱️ Timeout (45s) - forcing finalize for ${userId}`);
      this.finalizeTranscription('timeout');
    }, this.MAX_SPEAKING_TIME_MS);
    
    return true;
  }

  /**
   * Handle user stopping speaking
   */
  onSpeakingEnd(userId) {
    // Only process if this is the active speaker
    if (this.activeSpeaker !== userId) {
      return;
    }

    console.log(`🔇 ${userId} stopped speaking - waiting for silence confirmation`);
    
    // Start silence detection timer
    this.startSilenceDetection();
  }

  /**
   * Handle incoming audio data
   * Updates last audio time for silence detection
   */
  onAudioData(userId) {
    if (this.activeSpeaker !== userId) {
      return;
    }

    this.lastAudioTime = Date.now();
    
    // Reset silence timer if it's running
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.startSilenceDetection();
    }
  }

  /**
   * Start silence detection timer
   */
  startSilenceDetection() {
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
    }

    this.silenceTimer = setTimeout(() => {
      const silenceDuration = Date.now() - this.lastAudioTime;
      if (silenceDuration >= this.SILENCE_THRESHOLD_MS) {
        console.log(`🤫 Silence detected (${silenceDuration}ms) - finalizing transcription`);
        this.finalizeTranscription('silence');
      }
    }, this.SILENCE_THRESHOLD_MS);
  }

  /**
   * Start Whisper transcription stream
   */
  startTranscription(userId, opusStream) {
    try {
      this.whisperClient = new WhisperClient();
      this.whisperClient.connect(userId);
      
      // Pipe Opus audio to Whisper
      opusStream.on('data', (chunk) => {
        this.onAudioData(userId);
        this.whisperClient.sendAudio(chunk);
      });

      opusStream.on('end', () => {
        console.log(`📡 Opus stream ended for ${userId}`);
      });

      opusStream.on('error', (error) => {
        if (!error.message.includes('EOF')) {
          console.error(`❌ Opus stream error for ${userId}:`, error.message);
        }
      });

    } catch (error) {
      console.error(`❌ Error starting transcription for ${userId}:`, error.message);
      this.unlock();
    }
  }

  /**
   * Finalize transcription and send to n8n
   */
  async finalizeTranscription(reason) {
    if (!this.activeSpeaker || !this.whisperClient) {
      return;
    }

    const userId = this.activeSpeaker;
    const speakingDuration = Date.now() - this.lockStartTime;

    console.log(`✅ Finalizing transcription for ${userId} (reason: ${reason}, duration: ${speakingDuration}ms)`);

    try {
      // Get final transcript from Whisper
      const transcript = await this.whisperClient.finalize();

      if (transcript && transcript.trim().length > 0) {
        console.log(`📝 Final transcript from ${userId}: "${transcript}"`);
        
        // Send to n8n webhook
        await this.sendTranscriptToN8n(userId, transcript);
      } else {
        console.log(`⚠️ No transcript received for ${userId}`);
      }

    } catch (error) {
      console.error(`❌ Error finalizing transcription for ${userId}:`, error.message);
    } finally {
      // Always unlock, even if there was an error
      this.unlock();
    }
  }

  /**
   * Set voice connection for audio playback
   */
  setVoiceConnection(voiceConnection) {
    this.voiceConnection = voiceConnection;
    console.log('🔊 Voice connection set for audio playback');
  }

  /**
   * Send transcript to n8n webhook (with optional streaming support)
   */
  async sendTranscriptToN8n(userId, transcript) {
    if (!this.N8N_WEBHOOK_URL) {
      console.log('⚠️ N8N_WEBHOOK_URL not configured, skipping transcript send');
      return;
    }

    try {
      if (this.USE_STREAMING && this.voiceConnection) {
        // Use streaming mode
        console.log('🌊 Using streaming mode for n8n response');
        await this.streamResponseFromN8n(userId, transcript);
      } else {
        // Use traditional mode (non-streaming)
        console.log('📦 Using traditional mode for n8n response');
        const response = await axios.post(this.N8N_WEBHOOK_URL, {
          userId: userId,
          transcript: transcript,
          timestamp: new Date().toISOString(),
          source: 'voice'
        }, {
          timeout: 5000
        });

        console.log('✉️ Transcript sent to n8n successfully');
      }

    } catch (error) {
      if (error.response) {
        console.error(`❌ n8n webhook error: ${error.response.status} - ${error.response.statusText}`);
      } else {
        console.error('❌ Error sending to n8n:', error.message);
      }
    }
  }

  /**
   * Stream response from n8n webhook
   */
  async streamResponseFromN8n(userId, transcript) {
    try {
      console.log(`🌊 Streaming AI response for ${userId}`);
      
      // POST to n8n webhook and expect streaming response
      const response = await axios({
        method: 'POST',
        url: this.N8N_WEBHOOK_URL,
        data: {
          userId: userId,
          transcript: transcript,
          timestamp: new Date().toISOString(),
          source: 'voice',
          streaming: true // Signal n8n to stream response
        },
        responseType: 'stream',
        timeout: 60000 // 60 second timeout for streaming
      });

      // Read streamed response from n8n
      const decoder = new TextDecoder();
      let buffer = '';
      let options = {}; // TTS options from n8n
      let contentStarted = false; // Track if we've parsed the initial JSON

      response.data.on('data', async (chunk) => {
        const text = decoder.decode(chunk, { stream: true });
        buffer += text;
        
        // If we haven't parsed options yet, try to parse first chunk as JSON
        if (!contentStarted && buffer.trim().length > 0) {
          try {
            // Try to parse as JSON (n8n response format)
            const jsonMatch = buffer.match(/\{[\s\S]*"output"[\s\S]*"options"[\s\S]*\}/);
            if (jsonMatch) {
              const parsed = JSON.parse(jsonMatch[0]);
              if (parsed.output && parsed.options) {
                console.log(`📦 Parsed n8n response format`);
                options = parsed.options || {};
                console.log(`📋 Extracted TTS options:`, options);
                
                // Create streaming handler with options
                this.streamingHandler = new StreamingResponseHandler(this.voiceConnection, userId, options);
                
                // Get content and start processing
                buffer = parsed.output.content || '';
                contentStarted = true;
                
                // Process any complete sentences already in content
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                  if (line.trim()) {
                    await this.streamingHandler.onChunk(line.trim());
                  }
                }
                return; // Skip the normal line processing
              }
            }
            
            // If no JSON match after a reasonable buffer, treat as plain text
            if (buffer.length > 100 && !contentStarted) {
              console.log(`📝 No JSON format detected, treating as plain text stream`);
              this.streamingHandler = new StreamingResponseHandler(this.voiceConnection, userId, {});
              contentStarted = true;
            }
          } catch (error) {
            // Not JSON, treat as plain text after enough buffer
            if (buffer.length > 100 && !contentStarted) {
              console.log(`📝 Plain text stream detected`);
              this.streamingHandler = new StreamingResponseHandler(this.voiceConnection, userId, {});
              contentStarted = true;
            }
          }
        }
        
        // If we have a handler, process lines
        if (contentStarted && this.streamingHandler) {
          // Process line by line (assuming n8n sends line-delimited chunks)
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer
          
          for (const line of lines) {
            if (line.trim()) {
              await this.streamingHandler.onChunk(line.trim());
            }
          }
        }
      });

      response.data.on('end', async () => {
        console.log('🏁 n8n stream ended');
        
        // Process any remaining buffer
        if (buffer.trim()) {
          await this.streamingHandler.onChunk(buffer.trim());
        }
        
        // Finalize streaming handler
        await this.streamingHandler.finalize();
        this.streamingHandler = null;
        
        console.log('✅ Streaming response complete');
      });

      response.data.on('error', (error) => {
        console.error('❌ n8n stream error:', error.message);
        if (this.streamingHandler) {
          this.streamingHandler.stop();
          this.streamingHandler = null;
        }
      });

    } catch (error) {
      console.error('❌ Error in streaming response:', error.message);
      if (this.streamingHandler) {
        this.streamingHandler.stop();
        this.streamingHandler = null;
      }
      throw error;
    }
  }

  /**
   * Unlock speaker and clean up resources
   */
  unlock() {
    console.log(`🔓 Unlocking speaker: ${this.activeSpeaker}`);

    // Clear timers
    if (this.timeoutTimer) {
      clearTimeout(this.timeoutTimer);
      this.timeoutTimer = null;
    }

    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }

    // Close Whisper client
    if (this.whisperClient) {
      this.whisperClient.close();
      this.whisperClient = null;
    }

    // Reset state
    this.activeSpeaker = null;
    this.lockStartTime = null;
    this.lastAudioTime = null;

    console.log('✅ Ready for next speaker');
  }

  /**
   * Get current speaker status
   */
  getStatus() {
    if (!this.activeSpeaker) {
      return {
        locked: false,
        activeSpeaker: null
      };
    }

    return {
      locked: true,
      activeSpeaker: this.activeSpeaker,
      speakingDuration: Date.now() - this.lockStartTime,
      silenceDuration: Date.now() - this.lastAudioTime
    };
  }

  /**
   * Force unlock (for cleanup)
   */
  forceUnlock() {
    if (this.activeSpeaker) {
      console.log(`⚠️ Force unlocking speaker: ${this.activeSpeaker}`);
      this.unlock();
    }
  }
}

module.exports = SpeakerManager;
