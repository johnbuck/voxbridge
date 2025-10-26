/**
 * Chatterbox TTS Settings Page
 * TTS configuration and settings
 */

import { TTSSettings } from '@/components/TTSSettings';

export function ChatterboxTTSPage() {
  return (
    <div className="min-h-screen bg-page-background p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-4xl font-bold">Chatterbox TTS Settings</h1>
          <p className="text-muted-foreground mt-1">
            Configure text-to-speech voice settings and streaming options
          </p>
        </div>

        {/* TTS Settings */}
        <TTSSettings />
      </div>
    </div>
  );
}
