// ============================================================
// Streaming Response Handler
// Handles streaming AI responses from n8n webhook
// - Receives text chunks as they arrive from AI
// - Buffers and extracts complete sentences
// - Sends sentences to Chatterbox TTS streaming endpoint
// - Plays audio immediately as it's generated
// ============================================================

const { createAudioPlayer, createAudioResource, StreamType } = require('@discordjs/voice');
const { PassThrough } = require('stream');
const axios = require('axios');

class StreamingResponseHandler {
  constructor(voiceConnection, userId, options = {}) {
    this.voiceConnection = voiceConnection;
    this.userId = userId;
    this.buffer = '';
    this.sentenceQueue = [];
    this.isProcessing = false;
    this.currentPlayer = null;
    this.options = options; // TTS options from n8n
    this.optionsParsed = false; // Track if we've parsed options from first chunk
    
    // Configuration
    this.CHATTERBOX_URL = process.env.CHATTERBOX_URL || 'http://localhost:8000';
    this.CHATTERBOX_VOICE_ID = process.env.CHATTERBOX_VOICE_ID;
    this.SENTENCE_DELIMITERS = /[.!?\n]+/;
    this.MIN_SENTENCE_LENGTH = 3; // Ignore very short fragments
    
    console.log(`📋 StreamingResponseHandler initialized with options:`, this.options);
  }

  /**
   * Handle incoming text chunk from n8n streaming webhook
   */
  async onChunk(textChunk) {
    if (!textChunk) return;
    
    console.log(`📨 Received chunk: "${textChunk}"`);
    this.buffer += textChunk;
    
    // Extract complete sentences
    const sentences = this.extractSentences();
    
    if (sentences.length > 0) {
      console.log(`✂️ Extracted ${sentences.length} sentence(s)`);
      this.sentenceQueue.push(...sentences);
      
      // Start processing queue if not already processing
      if (!this.isProcessing) {
        this.processQueue();
      }
    }
  }

  /**
   * Extract complete sentences from buffer
   * Returns array of sentences and updates buffer with remainder
   */
  extractSentences() {
    const sentences = [];
    let lastIndex = 0;
    
    // Find all sentence delimiters
    const matches = [...this.buffer.matchAll(this.SENTENCE_DELIMITERS)];
    
    for (const match of matches) {
      const endIndex = match.index + match[0].length;
      const sentence = this.buffer.substring(lastIndex, endIndex).trim();
      
      // Only add if sentence is long enough
      if (sentence.length >= this.MIN_SENTENCE_LENGTH) {
        sentences.push(sentence);
      }
      
      lastIndex = endIndex;
    }
    
    // Update buffer to keep incomplete sentence
    this.buffer = this.buffer.substring(lastIndex).trim();
    
    return sentences;
  }

  /**
   * Process sentence queue sequentially
   */
  async processQueue() {
    this.isProcessing = true;
    
    while (this.sentenceQueue.length > 0) {
      const sentence = this.sentenceQueue.shift();
      console.log(`🎵 Processing: "${sentence}"`);
      
      try {
        await this.synthesizeAndPlay(sentence);
      } catch (error) {
        console.error(`❌ Error processing sentence:`, error.message);
        // Continue with next sentence even if this one fails
      }
    }
    
    this.isProcessing = false;
  }

  /**
   * Send text to Chatterbox TTS streaming endpoint and play audio
   */
  async synthesizeAndPlay(text) {
    try {
      console.log(`🔊 Synthesizing: "${text}"`);
      
      // Build TTS request with options from n8n (or defaults)
      const ttsData = {
        text: text,
        language_id: 'en'
      };
      
      // Add voice parameter
      if (this.options.voiceMode === 'clone' && this.options.referenceAudioFilename) {
        ttsData.voice = this.options.referenceAudioFilename;
      } else if (this.CHATTERBOX_VOICE_ID) {
        ttsData.voice = this.CHATTERBOX_VOICE_ID;
      }
      
      // Add optional TTS parameters from n8n
      if (this.options.exaggeration !== undefined) {
        ttsData.exaggeration = parseFloat(this.options.exaggeration);
      } else {
        ttsData.exaggeration = 0.5; // Default
      }
      
      if (this.options.cfgWeight !== undefined) {
        ttsData.cfg_weight = parseFloat(this.options.cfgWeight);
      } else {
        ttsData.cfg_weight = 0.5; // Default
      }
      
      if (this.options.temperature !== undefined) {
        ttsData.temperature = parseFloat(this.options.temperature);
      }
      
      if (this.options.seed !== undefined) {
        ttsData.seed = parseInt(this.options.seed);
      }
      
      if (this.options.speedFactor !== undefined) {
        ttsData.speed = parseFloat(this.options.speedFactor);
      }
      
      if (this.options.outputFormat) {
        ttsData.response_format = this.options.outputFormat;
      }
      
      // Streaming-specific options
      if (this.options.streamingStrategy) {
        ttsData.streaming_strategy = this.options.streamingStrategy;
      }
      
      if (this.options.streamingQuality) {
        ttsData.streaming_quality = this.options.streamingQuality;
      }
      
      if (this.options.chunkSize) {
        ttsData.streaming_chunk_size = parseInt(this.options.chunkSize);
      }
      
      console.log(`📋 TTS request data:`, ttsData);
      
      // POST to Chatterbox streaming endpoint
      const response = await axios({
        method: 'POST',
        url: `${this.CHATTERBOX_URL}/audio/speech/stream`,
        data: ttsData,
        responseType: 'stream',
        timeout: 30000 // 30 second timeout
      });

      // Create audio player and stream
      const audioPlayer = createAudioPlayer();
      const audioStream = new PassThrough();
      
      // Create audio resource from stream
      const resource = createAudioResource(audioStream, {
        inputType: StreamType.Arbitrary,
      });
      
      // Play audio
      audioPlayer.play(resource);
      this.voiceConnection.subscribe(audioPlayer);
      this.currentPlayer = audioPlayer;

      // Pipe Chatterbox audio stream to Discord
      let receivedBytes = 0;
      response.data.on('data', (chunk) => {
        receivedBytes += chunk.length;
        audioStream.write(chunk);
      });

      response.data.on('end', () => {
        console.log(`✅ Received ${receivedBytes} bytes of audio`);
        audioStream.end();
      });

      response.data.on('error', (error) => {
        console.error('❌ Stream error:', error.message);
        audioStream.end();
      });

      // Wait for playback to complete
      await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error('Audio playback timeout'));
        }, 60000); // 60 second max playback time

        audioPlayer.on('idle', () => {
          clearTimeout(timeout);
          resolve();
        });

        audioPlayer.on('error', (error) => {
          clearTimeout(timeout);
          console.error('❌ Audio player error:', error.message);
          reject(error);
        });
      });

      console.log(`🎉 Finished playing: "${text}"`);

    } catch (error) {
      if (error.code === 'ECONNREFUSED') {
        console.error(`❌ Cannot connect to Chatterbox at ${this.CHATTERBOX_URL}`);
      } else {
        console.error(`❌ TTS error:`, error.message);
      }
      throw error;
    }
  }

  /**
   * Finalize processing - handle any remaining buffered text
   */
  async finalize() {
    console.log('🏁 Finalizing streaming response handler');
    
    // Process any remaining buffer
    if (this.buffer.trim().length >= this.MIN_SENTENCE_LENGTH) {
      console.log(`📝 Processing final buffer: "${this.buffer}"`);
      this.sentenceQueue.push(this.buffer.trim());
      this.buffer = '';
    }
    
    // Process remaining queue
    if (this.sentenceQueue.length > 0) {
      await this.processQueue();
    }
    
    console.log('✅ Streaming complete');
  }

  /**
   * Stop current playback and clean up
   */
  stop() {
    if (this.currentPlayer) {
      this.currentPlayer.stop();
      this.currentPlayer = null;
    }
    
    this.sentenceQueue = [];
    this.buffer = '';
    this.isProcessing = false;
    
    console.log('⏹️ Streaming response handler stopped');
  }
}

module.exports = StreamingResponseHandler;
