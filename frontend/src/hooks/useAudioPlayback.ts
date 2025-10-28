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
      if (chunks.length === 0) {
        console.warn('⚠️ No audio chunks to play');
        return;
      }

      options.onPlaybackStart?.();
      setIsPlaying(true);

      // Concatenate all chunks into single blob
      const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const combined = new Uint8Array(totalLength);
      let offset = 0;
      for (const chunk of chunks) {
        combined.set(chunk, offset);
        offset += chunk.length;
      }

      // Create WAV blob
      const audioBlob = new Blob([combined], { type: 'audio/wav' });
      const audioUrl = URL.createObjectURL(audioBlob);

      // Create audio element
      const audio = new Audio(audioUrl);
      audio.volume = isMuted ? 0 : volume;
      audioRef.current = audio;

      // Play audio
      await audio.play();

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
    if (audioChunksRef.current.length === 0) {
      console.warn('⚠️ No audio chunks buffered');
      return;
    }

    await playAudioChunks(audioChunksRef.current);
    audioChunksRef.current = [];
  }, [playAudioChunks]);

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
