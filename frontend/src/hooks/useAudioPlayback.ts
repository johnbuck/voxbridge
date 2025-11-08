/**
 * Audio Playback Hook for WebRTC TTS
 *
 * Handles playback of TTS audio received via WebSocket binary frames.
 * Supports both streaming chunks and complete WAV files.
 */

import { useState, useCallback, useRef, useEffect } from 'react';

export interface UseAudioPlaybackOptions {
  autoPlay?: boolean;
  onPlaybackStart?: () => void;
  onPlaybackEnd?: () => void;
  onError?: (error: string) => void;
}

export interface UseAudioPlaybackReturn {
  isPlaying: boolean;
  isMuted: boolean;
  volume: number;
  setVolume: (volume: number) => void;
  toggleMute: () => void;
  playAudioChunks: (chunks: Uint8Array[]) => Promise<void>;
  stop: () => void;
  addAudioChunk: (chunk: Uint8Array) => void;
  completeAudio: () => Promise<void>;
}

export function useAudioPlayback(options: UseAudioPlaybackOptions = {}): UseAudioPlaybackReturn {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [volume, setVolumeState] = useState(1.0);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioChunksRef = useRef<Uint8Array[]>([]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stop();
    };
  }, []);

  const setVolume = useCallback((vol: number) => {
    const clampedVolume = Math.max(0, Math.min(1, vol));
    setVolumeState(clampedVolume);
    if (audioRef.current) {
      audioRef.current.volume = isMuted ? 0 : clampedVolume;
    }
  }, [isMuted]);

  const toggleMute = useCallback(() => {
    setIsMuted(!isMuted);
    if (audioRef.current) {
      audioRef.current.volume = !isMuted ? 0 : volume;
    }
  }, [isMuted, volume]);

  const playAudioChunks = useCallback(async (chunks: Uint8Array[]) => {
    try {
      console.log(`🔍 DEBUG: playAudioChunks() called with ${chunks.length} chunks`);
      if (chunks.length === 0) {
        console.warn('⚠️ No audio chunks to play');
        return;
      }

      options.onPlaybackStart?.();
      setIsPlaying(true);

      // Concatenate all chunks into single blob
      const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      console.log(`🔍 DEBUG: Total audio size: ${totalLength} bytes (${(totalLength / 1024).toFixed(2)} KB)`);
      const combined = new Uint8Array(totalLength);
      let offset = 0;
      for (const chunk of chunks) {
        combined.set(chunk, offset);
        offset += chunk.length;
      }

      // Create WAV blob
      const audioBlob = new Blob([combined], { type: 'audio/wav' });
      const audioUrl = URL.createObjectURL(audioBlob);
      console.log(`🔍 DEBUG: Created WAV blob: ${audioBlob.size} bytes, URL: ${audioUrl}`);

      // Create audio element
      const audio = new Audio(audioUrl);
      audio.volume = isMuted ? 0 : volume;
      audioRef.current = audio;
      console.log(`🔍 DEBUG: Created Audio element, volume=${audio.volume}, muted=${isMuted}`);

      // Play audio
      console.log('🔍 DEBUG: Calling audio.play()...');
      await audio.play();
      console.log('🔍 DEBUG: audio.play() succeeded!');

      // Wait for completion
      audio.onended = () => {
        setIsPlaying(false);
        options.onPlaybackEnd?.();
        URL.revokeObjectURL(audioUrl);
        audioRef.current = null;
      };

      audio.onerror = (e) => {
        const errorMsg = `Audio playback error: ${e}`;
        console.error('❌', errorMsg);
        options.onError?.(errorMsg);
        setIsPlaying(false);
        URL.revokeObjectURL(audioUrl);
        audioRef.current = null;
      };

    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Playback failed';
      console.error('❌ Audio playback error:', errorMsg);
      options.onError?.(errorMsg);
      setIsPlaying(false);
    }
  }, [volume, isMuted, options]);

  const addAudioChunk = useCallback((chunk: Uint8Array) => {
    audioChunksRef.current.push(chunk);
  }, []);

  const completeAudio = useCallback(async () => {
    console.log(`🔍 DEBUG: completeAudio() called, ${audioChunksRef.current.length} chunks buffered`);

    // Fix #1: Wait for audio chunks to arrive (race condition fix)
    // tts_complete event may arrive before binary audio chunks due to different TCP buffers
    const MAX_WAIT_MS = 500;
    const startTime = Date.now();

    while (audioChunksRef.current.length === 0 && (Date.now() - startTime) < MAX_WAIT_MS) {
      console.log(`⏳ Waiting for audio chunks... (elapsed: ${Date.now() - startTime}ms)`);
      await new Promise(resolve => setTimeout(resolve, 50)); // Check every 50ms
    }

    if (audioChunksRef.current.length === 0) {
      const errorMsg = 'No audio data received after waiting 500ms';
      console.error('❌', errorMsg);
      options.onError?.(errorMsg);
      return;
    }

    console.log(`✅ Audio chunks arrived after ${Date.now() - startTime}ms`);
    await playAudioChunks(audioChunksRef.current);
    console.log('🔍 DEBUG: playAudioChunks() completed, clearing buffer');
    audioChunksRef.current = [];
  }, [playAudioChunks, options]);

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    audioChunksRef.current = [];
    setIsPlaying(false);
  }, []);

  return {
    isPlaying,
    isMuted,
    volume,
    setVolume,
    toggleMute,
    playAudioChunks,
    stop,
    addAudioChunk,
    completeAudio,
  };
}
