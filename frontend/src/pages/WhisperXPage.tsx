/**
 * WhisperX STT Page
 * Placeholder for future WhisperX controls
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function WhisperXPage() {
  return (
    <div className="min-h-screen bg-page-background p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-4xl font-bold">WhisperX Controls</h1>
          <p className="text-muted-foreground mt-1">
            Speech-to-text service configuration
          </p>
        </div>

        {/* Placeholder Card */}
        <Card>
          <CardHeader>
            <CardTitle>Coming Soon</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center py-12 text-muted-foreground">
              <p className="text-sm">WhisperX controls will be available here in the future.</p>
              <p className="text-xs mt-2">
                This page will allow you to configure WhisperX settings, view transcription logs, and manage STT preferences.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
