/**
 * TTS Test Modal Component
 * Modal dialog for testing text-to-speech with an agent's voice settings
 */

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Volume2, Loader2 } from 'lucide-react';
import { api, type Agent } from '@/services/api';

interface TTSTestModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agent: Agent;
}

const DEFAULT_TEST_MESSAGES = [
  "Hello! This is a test of the text-to-speech system.",
  "The quick brown fox jumps over the lazy dog.",
  "I'm an AI assistant powered by VoxBridge. How can I help you today?",
  "Testing one, two, three. Can you hear me clearly?"
];

export function TTSTestModal({ open, onOpenChange, agent }: TTSTestModalProps) {
  const [text, setText] = useState(DEFAULT_TEST_MESSAGES[0]);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const handleSpeak = async () => {
    if (!text.trim()) return;

    setIsSpeaking(true);
    try {
      // Build TTS options based on agent configuration
      const options: any = {};

      if (agent.tts_voice) {
        options.voiceId = agent.tts_voice;
      }

      if (agent.tts_rate !== 1.0) {
        options.speedFactor = agent.tts_rate;
      }

      // Note: pitch adjustment requires backend support
      // Adding as a comment for future implementation
      // if (agent.tts_pitch !== 1.0) {
      //   options.pitch = agent.tts_pitch;
      // }

      await api.speak(text, options);
    } catch (error) {
      console.error('Failed to test TTS:', error);
      alert(`Failed to test TTS: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsSpeaking(false);
    }
  };

  const handleQuickTest = (message: string) => {
    setText(message);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Test TTS - {agent.name}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Voice Settings Display */}
          <div className="space-y-2 p-3 rounded bg-muted">
            <div className="text-sm font-medium">Current Voice Settings</div>
            <div className="text-xs space-y-1">
              {agent.tts_voice && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Voice ID:</span>
                  <span className="font-mono">{agent.tts_voice}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">Speech Rate:</span>
                <span>{agent.tts_rate}x</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Pitch:</span>
                <span>{agent.tts_pitch}x</span>
              </div>
            </div>
          </div>

          {/* Quick Test Buttons */}
          <div className="space-y-2">
            <Label>Quick Test Messages</Label>
            <div className="flex flex-wrap gap-2">
              {DEFAULT_TEST_MESSAGES.map((msg, idx) => (
                <Button
                  key={idx}
                  variant="outline"
                  size="sm"
                  onClick={() => handleQuickTest(msg)}
                  disabled={isSpeaking}
                  className="text-xs"
                >
                  Test {idx + 1}
                </Button>
              ))}
            </div>
          </div>

          {/* Custom Text Input */}
          <div className="space-y-2">
            <Label htmlFor="ttsText">Custom Text</Label>
            <Textarea
              id="ttsText"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Enter text to speak..."
              rows={4}
              maxLength={500}
              disabled={isSpeaking}
            />
            <p className="text-xs text-muted-foreground">
              {text.length} / 500 characters
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSpeaking}
          >
            Close
          </Button>
          <Button
            onClick={handleSpeak}
            disabled={isSpeaking || !text.trim()}
          >
            {isSpeaking ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Speaking...
              </>
            ) : (
              <>
                <Volume2 className="mr-2 h-4 w-4" />
                Speak
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
