/**
 * Settings Hub Page
 * Main settings page with sidebar navigation and overview cards
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SettingsSidebar } from '@/components/SettingsSidebar';
import { Link, useLocation } from 'wouter';
import { Settings, Mic, Volume2, Plug, Brain, Database, User } from 'lucide-react';
import { WhisperXSettingsPage } from './settings/WhisperXSettingsPage';
import { ChatterboxSettingsPage } from './settings/ChatterboxSettingsPage';
import { PluginsSettingsPage } from './settings/PluginsSettingsPage';
import { EmbeddingsSettingsPage } from './settings/EmbeddingsSettingsPage';
import { MemorySettingsPage } from './settings/MemorySettingsPage';
import { AccountSettingsPage } from './settings/AccountSettingsPage';
import { LLMProvidersPage } from './LLMProvidersPage';

/**
 * Overview Cards Component
 * Displays clickable cards for each settings category
 */
function OverviewCards() {
  return (
    <>
      <div className="mb-6">
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <Settings className="h-8 w-8" />
          Settings
        </h1>
        <p className="text-muted-foreground mt-2">
          Configure VoxBridge services and integrations
        </p>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Link href="/settings/account">
          <Card className="hover:border-primary/50 cursor-pointer transition-colors">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <User className="h-5 w-5" />
                Account
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Change password and manage account settings
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/settings/llm-providers">
          <Card className="hover:border-primary/50 cursor-pointer transition-colors">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Brain className="h-5 w-5" />
                LLM Providers
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Manage OpenAI-compatible API endpoints
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/settings/memory">
          <Card className="hover:border-primary/50 cursor-pointer transition-colors">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Brain className="h-5 w-5" />
                Memory
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Configure memory extraction and data management
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/settings/whisperx">
          <Card className="hover:border-primary/50 cursor-pointer transition-colors">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mic className="h-5 w-5" />
                WhisperX STT
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Configure speech-to-text service
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/settings/chatterbox">
          <Card className="hover:border-primary/50 cursor-pointer transition-colors">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Volume2 className="h-5 w-5" />
                Chatterbox TTS
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Configure text-to-speech service
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/settings/embeddings">
          <Card className="hover:border-primary/50 cursor-pointer transition-colors">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5" />
                Embeddings
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Configure global embedding provider for memory system
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/settings/plugins">
          <Card className="hover:border-primary/50 cursor-pointer transition-colors">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Plug className="h-5 w-5" />
                Plugins
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Manage installed plugins and extensions
              </p>
            </CardContent>
          </Card>
        </Link>
      </div>
    </>
  );
}

export function SettingsPage() {
  const [location] = useLocation();

  // Determine which content to show based on location
  let content;
  if (location === '/settings') {
    content = <OverviewCards />;
  } else if (location === '/settings/account') {
    content = <AccountSettingsPage />;
  } else if (location === '/settings/llm-providers') {
    content = <LLMProvidersPage />;
  } else if (location === '/settings/memory') {
    content = <MemorySettingsPage />;
  } else if (location === '/settings/whisperx') {
    content = <WhisperXSettingsPage />;
  } else if (location === '/settings/chatterbox') {
    content = <ChatterboxSettingsPage />;
  } else if (location === '/settings/embeddings') {
    content = <EmbeddingsSettingsPage />;
  } else if (location === '/settings/plugins') {
    content = <PluginsSettingsPage />;
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 md:py-8">
      <div className="flex gap-6">
        {/* Sidebar Navigation - Hidden on mobile, visible on desktop */}
        <aside className="hidden md:block w-64 flex-shrink-0">
          <SettingsSidebar />
        </aside>

        {/* Main Content Area */}
        <div className="flex-1 min-w-0">
          {content}
        </div>
      </div>
    </div>
  );
}
