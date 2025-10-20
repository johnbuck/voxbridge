// ============================================================
// Discord Bot Voice Service
// Handles voice channel operations for Auren bot:
// - Join/leave voice channels
// - Speech-to-Text (WhisperX)
// - Text-to-Speech (Chatterbox TTS)
// - Send transcripts back to n8n for agent processing
// ============================================================

require('dotenv').config();
const { Client, GatewayIntentBits } = require('discord.js');
const { 
  joinVoiceChannel, 
  createAudioPlayer, 
  createAudioResource, 
  EndBehaviorType,
  VoiceConnectionStatus 
} = require('@discordjs/voice');
const express = require('express');
const axios = require('axios');
const WhisperClient = require('./whisper-client');
const SpeakerManager = require('./speaker-manager');

// ============================================================
// CONFIGURATION
// ============================================================

const app = express();
app.use(express.json());

// Discord client with necessary intents
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,           // Access to guild information
    GatewayIntentBits.GuildVoiceStates, // Voice state updates
    GatewayIntentBits.GuildMessages     // Message access (if needed)
  ]
});

// Voice connection state
let voiceConnection = null;
let audioPlayer = createAudioPlayer();

// Speaker manager for single-speaker lock (defined at bottom of file)
let speakerManager = null;

// ============================================================
// INITIALIZATION
// ============================================================

// Discord client ready event
client.once('ready', () => {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`✅ Discord bot logged in as ${client.user.tag}`);
  console.log(`🎙️ Voice service ready with WhisperX STT`);
  console.log(`${'='.repeat(60)}\n`);
});

// Handle Discord client errors
client.on('error', (error) => {
  console.error(`❌ Discord client error:`, error);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log(`\n⚠️ SIGTERM received - shutting down gracefully...`);
  speakerManager.forceUnlock();
  if (voiceConnection) {
    voiceConnection.destroy();
  }
  client.destroy();
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log(`\n⚠️ SIGINT received - shutting down gracefully...`);
  speakerManager.forceUnlock();
  if (voiceConnection) {
    voiceConnection.destroy();
  }
  client.destroy();
  process.exit(0);
});

// Login to Discord
console.log(`🔐 Logging in to Discord...`);
client.login(process.env.DISCORD_TOKEN).catch(error => {
  console.error(`❌ Failed to login to Discord:`, error);
  process.exit(1);
});

// Start Express server
const PORT = process.env.PORT || 4900;
app.listen(PORT, () => {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`🚀 Voice bot API listening on port ${PORT}`);
  console.log(`📍 Endpoints available:`);
  console.log(`   POST /voice/join - Join voice channel`);
  console.log(`   POST /voice/leave - Leave voice channel`);
  console.log(`   POST /voice/speak - Speak text via TTS`);
  console.log(`   GET  /health - Health check`);
  console.log(`   GET  /status - Detailed status`);
  console.log(`${'='.repeat(60)}\n`);
});

// ============================================================
// VOICE CHANNEL OPERATIONS
// ============================================================

/**
 * JOIN VOICE CHANNEL
 * Connects bot to specified voice channel and sets up audio listeners
 */
app.post('/voice/join', async (req, res) => {
  const { channelId, guildId } = req.body;
  
  console.log(`📞 JOIN request received - Channel: ${channelId}, Guild: ${guildId}`);
  
  // Validate required parameters
  if (!channelId || !guildId) {
    console.error(`❌ Missing parameters`);
    return res.status(400).json({ 
      error: 'Missing required parameters: channelId and guildId' 
    });
  }
  
  try {
    // Fetch the voice channel from Discord
    console.log(`   🔍 Fetching channel from Discord...`);
    const channel = await client.channels.fetch(channelId);
    
    if (!channel || channel.type !== 2) { // 2 = GUILD_VOICE
      console.error(`❌ Invalid voice channel`);
      return res.status(400).json({ error: 'Invalid voice channel' });
    }
    
    console.log(`   ✅ Channel found: ${channel.name}`);
    
    // Create voice connection
    console.log(`   🔌 Creating voice connection...`);
    voiceConnection = joinVoiceChannel({
      channelId: channelId,
      guildId: guildId,
      adapterCreator: channel.guild.voiceAdapterCreator,
      selfDeaf: false,  // Bot needs to hear
      selfMute: false   // Bot needs to speak
    });
    
    // Subscribe audio player to connection
    voiceConnection.subscribe(audioPlayer);
    console.log(`   🔊 Audio player subscribed`);
    
    // Pass voice connection to speaker manager for streaming support
    speakerManager.setVoiceConnection(voiceConnection);
    console.log(`   🌊 Voice connection passed to speaker manager for streaming`);
    
    // Handle connection state changes
    voiceConnection.on(VoiceConnectionStatus.Ready, () => {
      console.log(`✅ Voice connection READY`);
    });
    
    voiceConnection.on(VoiceConnectionStatus.Disconnected, () => {
      console.log(`⚠️ Voice connection DISCONNECTED`);
    });
    
    voiceConnection.on(VoiceConnectionStatus.Destroyed, () => {
      console.log(`💥 Voice connection DESTROYED`);
    });
    
    // Listen for users speaking
    console.log(`   👂 Setting up speaking listeners...`);
    
    voiceConnection.receiver.speaking.on('start', async (userId) => {
      console.log(`\n👂 SPEAKING START EVENT - User: ${userId}`);
      
      // Get Opus audio stream for this user
      console.log(`   📡 Subscribing to audio stream...`);
      const opusStream = voiceConnection.receiver.subscribe(userId);
      console.log(`   ✅ Audio stream subscribed`);
      console.log(`   🔍 Stream readable: ${opusStream.readable}, destroyed: ${opusStream.destroyed}`);
      
      // Pass to speaker manager (will ignore if another speaker is active)
      await speakerManager.onSpeakingStart(userId, opusStream);
    });
    
    voiceConnection.receiver.speaking.on('end', (userId) => {
      console.log(`\n🔇 SPEAKING END EVENT - User: ${userId}`);
      speakerManager.onSpeakingEnd(userId);
    });
    
    console.log(`✅ Speaking listeners configured`);
    
    res.json({ 
      success: true, 
      message: `Joined voice channel: ${channel.name}`,
      channelId: channelId
    });
    
    console.log(`✅ JOIN complete - Now listening in ${channel.name}\n`);
    
  } catch (error) {
    console.error(`❌ Error joining voice channel:`, error.message);
    console.error(`   Stack:`, error.stack);
    res.status(500).json({ error: error.message });
  }
});

/**
 * LEAVE VOICE CHANNEL
 * Disconnects bot from current voice channel and cleans up resources
 */
app.post('/voice/leave', (req, res) => {
  console.log(`📞 LEAVE request received`);
  
  if (!voiceConnection) {
    console.log(`   ⚠️ Not in a voice channel`);
    return res.status(400).json({ error: 'Not currently in a voice channel' });
  }
  
  try {
    // Force unlock any active speaker
    speakerManager.forceUnlock();
    
    // Destroy voice connection
    voiceConnection.destroy();
    voiceConnection = null;
    
    console.log(`✅ Left voice channel\n`);
    res.json({ success: true, message: 'Left voice channel' });
    
  } catch (error) {
    console.error(`❌ Error leaving voice channel:`, error.message);
    res.status(500).json({ error: error.message });
  }
});

// ============================================================
// SPEAKER MANAGER INITIALIZATION
// Imported from speaker-manager.js (with streaming support)
// ============================================================

speakerManager = new SpeakerManager();

// ============================================================
// TEXT-TO-SPEECH (Chatterbox TTS)
// ============================================================

/**
 * SPEAK TEXT
 * Converts text to speech using Chatterbox TTS and plays in voice channel
 * Accepts n8n format with output.content and options for TTS parameters
 */
app.post('/voice/speak', async (req, res) => {
  const { output, options } = req.body;
  
  // Extract text from output.content
  const text = output?.content;
  
  console.log(`🔊 SPEAK request: "${text}"`);
  console.log(`📋 Options:`, options);
  
  if (!text) {
    return res.status(400).json({ error: 'Missing required parameter: output.content' });
  }
  
  if (!voiceConnection) {
    console.log(`   ⚠️ Not in a voice channel`);
    return res.status(400).json({ error: 'Not in a voice channel' });
  }
  
  try {
    console.log(`   📞 Requesting TTS from Chatterbox...`);
    
    // Build Chatterbox TTS request with all parameters for streaming endpoint
    const ttsRequest = {
      input: text,  // Required parameter
      response_format: options.outputFormat || 'wav',
      speed: parseFloat(options.speedFactor) || 1.0
    };

    // Add voice parameter - use voice name for cloning or predefined
    if (options.voiceMode === 'clone' && options.referenceAudioFilename) {
      ttsRequest.voice = options.referenceAudioFilename;
    } else {
      // Use environment variable as fallback for predefined voice
      ttsRequest.voice = process.env.CHATTERBOX_VOICE_ID || 'default';
    }

    // Add generation parameters with type conversion
    if (options.temperature) {
      ttsRequest.temperature = parseFloat(options.temperature);
    }
    if (options.exaggeration) {
      ttsRequest.exaggeration = parseFloat(options.exaggeration);
    }
    if (options.cfgWeight) {
      ttsRequest.cfg_weight = parseFloat(options.cfgWeight);
    }
    
    // Add streaming parameters
    if (options.chunkSize) {
      ttsRequest.streaming_chunk_size = parseInt(options.chunkSize);
    }
    
    // Add streaming strategy (sentence, paragraph, fixed, word)
    if (options.streamingStrategy) {
      ttsRequest.streaming_strategy = options.streamingStrategy;
    }
    
    // Add streaming quality (fast, balanced, high)  
    if (options.streamingQuality) {
      ttsRequest.streaming_quality = options.streamingQuality;
    }

    console.log(`   📋 TTS Request:`, ttsRequest);
    
    // Convert to FormData for multipart upload
    const FormData = require('form-data');
    const formData = new FormData();
    
    // Add all parameters as form fields
    Object.entries(ttsRequest).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        formData.append(key, value.toString());
      }
    });
    
    console.log(`   📋 FormData fields:`, Object.keys(ttsRequest));
    
    // Request TTS from Chatterbox server (streaming endpoint with FormData)
    const ttsResponse = await axios.post(
      `${process.env.CHATTERBOX_URL}/audio/speech/stream/upload`,
      formData,
      { 
        responseType: 'stream',
        timeout: 30000,  // 30 second timeout
        headers: {
          ...formData.getHeaders()
        }
      }
    );
    
    console.log(`   ✅ TTS response received`);
    
    // Create audio resource from TTS stream
    const resource = createAudioResource(ttsResponse.data, {
      inputType: 'arbitrary'  // Let Discord.js detect format
    });
    
    // Play audio in voice channel
    audioPlayer.play(resource);
    
    console.log(`✅ Playing audio in voice channel\n`);
    res.json({ success: true, message: 'Speaking text' });
    
  } catch (error) {
    console.error(`❌ Error with TTS:`, error.message);
    
    // Log detailed error information from Chatterbox TTS
    if (error.response) {
      console.error(`   � Chatterbox Response Status:`, error.response.status);
      console.error(`   📋 Chatterbox Response Headers:`, error.response.headers);
      
      // Handle stream responses safely
      if (error.response.data && error.response.data.readable) {
        console.error(`   📋 Chatterbox Response Data: [Stream - cannot display]`);
        // Try to read from stream if possible
        let chunks = [];
        error.response.data.on('data', (chunk) => {
          chunks.push(chunk);
        });
        error.response.data.on('end', () => {
          const responseText = Buffer.concat(chunks).toString();
          console.error(`   � Chatterbox Stream Response:`, responseText);
        });
      } else if (typeof error.response.data === 'string') {
        console.error(`   📋 Chatterbox Response Data (string):`, error.response.data);
      } else if (error.response.data && typeof error.response.data === 'object') {
        try {
          console.error(`   � Chatterbox Response Data (object):`, JSON.stringify(error.response.data, null, 2));
        } catch (stringifyError) {
          console.error(`   📋 Chatterbox Response Data: [Object - cannot stringify due to circular refs]`);
        }
      } else {
        console.error(`   📋 Chatterbox Response Data (raw):`, error.response.data);
      }
    } else if (error.request) {
      console.error(`   📋 Request made but no response:`, error.request);
    }
    
    res.status(500).json({ error: error.message });
  }
});

// ============================================================
// HEALTH & STATUS
// ============================================================

/**
 * Health check endpoint
 * Returns current bot status and connection state
 */
app.get('/health', (req, res) => {
  const speakerStatus = speakerManager.getStatus();
  res.json({ 
    status: 'ok',
    botReady: client.isReady(),
    inVoiceChannel: voiceConnection !== null,
    speakerLocked: speakerStatus.locked,
    activeSpeaker: speakerStatus.activeSpeaker,
    timestamp: new Date().toISOString()
  });
});

/**
 * Status endpoint with detailed information
 */
app.get('/status', (req, res) => {
  const speakerStatus = speakerManager.getStatus();
  res.json({
    bot: {
      username: client.user?.username || 'Not ready',
      id: client.user?.id || null,
      ready: client.isReady()
    },
    voice: {
      connected: voiceConnection !== null,
      state: voiceConnection?.state?.status || 'disconnected',
      speakerLocked: speakerStatus.locked,
      activeSpeaker: speakerStatus.activeSpeaker,
      speakingDuration: speakerStatus.speakingDuration,
      silenceDuration: speakerStatus.silenceDuration
    },
    whisperx: {
      serverConfigured: !!process.env.WHISPER_SERVER_URL,
      model: process.env.WHISPERX_MODEL || 'small',
      device: process.env.WHISPERX_DEVICE || 'auto',
      computeType: process.env.WHISPERX_COMPUTE_TYPE || 'float16',
      batchSize: process.env.WHISPERX_BATCH_SIZE || '16'
    },
    services: {
      chatterbox: !!process.env.CHATTERBOX_URL,
      n8nWebhook: !!process.env.N8N_WEBHOOK_URL
    }
  });
});
