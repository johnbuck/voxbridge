/**
 * TTS Test Component
 * Interface to test text-to-speech functionality
 */

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Slider } from '@/components/ui/slider';
import { Volume2 } from 'lucide-react';

interface TTSTestProps {
  inVoiceChannel: boolean;
}

export function TTSTest({ inVoiceChannel }: TTSTestProps) {
  const [text, setText] = useState('');
  const [speedFactor, setSpeedFactor] = useState([1.0]);

  const speakMutation = useMutation({
    mutationFn: ({ text, speed }: { text: string; speed: number }) =>
      api.speak(text, { speedFactor: speed }),
  });

  const handleSpeak = () => {
    if (text.trim()) {
      speakMutation.mutate({ text: text.trim(), speed: speedFactor[0] });
    }
  };

  const charCount = text.length;
  const maxChars = 500; // Reasonable limit for TTS

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Volume2 className="size-5" />
          TTS Testing
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Text Input */}
        <div className="space-y-2">
          <label htmlFor="tts-text" className="text-sm font-medium">
            Text to Speak
          </label>
          <Textarea
            id="tts-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Enter text to convert to speech..."
            maxLength={maxChars}
            className="min-h-24"
            disabled={!inVoiceChannel}
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{inVoiceChannel ? 'Ready to speak' : 'Not in voice channel'}</span>
            <span>
              {charCount} / {maxChars}
            </span>
          </div>
        </div>

        {/* Speed Control */}
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <label htmlFor="tts-speed" className="text-sm font-medium">
              Speed
            </label>
            <span className="text-sm text-muted-foreground">{speedFactor[0].toFixed(1)}x</span>
          </div>
          <Slider
            id="tts-speed"
            value={speedFactor}
            onValueChange={setSpeedFactor}
            min={0.5}
            max={2.0}
            step={0.1}
            disabled={!inVoiceChannel}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Slower (0.5x)</span>
            <span>Faster (2.0x)</span>
          </div>
        </div>

        {/* Speak Button */}
        <Button
          onClick={handleSpeak}
          disabled={!inVoiceChannel || !text.trim() || speakMutation.isPending}
          className="w-full"
        >
          {speakMutation.isPending ? 'Speaking...' : 'Speak'}
        </Button>

        {/* Error Display */}
        {speakMutation.isError && (
          <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-md">
            <p className="text-sm text-destructive">
              Error: {speakMutation.error?.message || 'Failed to generate speech'}
            </p>
          </div>
        )}

        {/* Success Display */}
        {speakMutation.isSuccess && (
          <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-md">
            <p className="text-sm text-green-700 dark:text-green-400">
              Audio sent to Discord voice channel
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
