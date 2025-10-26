#!/usr/bin/env python3
"""
Generate a subtle thinking indicator sound effect
Soft UI notification tone - gentle, non-intrusive
"""

import numpy as np
import wave
import struct

# Audio parameters
sample_rate = 48000  # Discord-compatible
duration = 1.2  # seconds
filename = "thinking_indicator.wav"

# Generate time array
t = np.linspace(0, duration, int(sample_rate * duration))

# Create a gentle two-tone notification sound
# Base frequency (C note, soft and pleasant)
freq1 = 523.25  # C5
freq2 = 659.25  # E5

# Generate tones with smooth envelope
tone1 = np.sin(2 * np.pi * freq1 * t)
tone2 = np.sin(2 * np.pi * freq2 * t)

# Create envelope (fade in, sustain, fade out)
fade_in_samples = int(0.05 * sample_rate)  # 50ms fade in
fade_out_samples = int(0.3 * sample_rate)  # 300ms fade out
sustain_samples = len(t) - fade_in_samples - fade_out_samples

envelope = np.ones(len(t))
envelope[:fade_in_samples] = np.linspace(0, 1, fade_in_samples)
envelope[-fade_out_samples:] = np.linspace(1, 0, fade_out_samples)

# Mix: start with tone1, blend to tone2, then fade out
blend = np.linspace(0, 1, len(t))
mixed_tone = tone1 * (1 - blend * 0.5) + tone2 * (blend * 0.5)

# Apply envelope and reduce amplitude for subtlety
audio = mixed_tone * envelope * 0.3  # 30% volume for subtlety

# Convert to 16-bit PCM
audio_int = np.int16(audio * 32767)

# Write WAV file
with wave.open(filename, 'w') as wav_file:
    # Set parameters: nchannels, sampwidth, framerate, nframes, comptype, compname
    wav_file.setparams((2, 2, sample_rate, len(audio_int), 'NONE', 'not compressed'))

    # Write stereo (duplicate mono to both channels)
    for sample in audio_int:
        wav_file.writeframes(struct.pack('<hh', sample, sample))

print(f"✅ Generated {filename} ({duration}s, {sample_rate}Hz)")
print(f"   Gentle two-tone notification (C5→E5)")
print(f"   30% volume, smooth fade-in/out")
