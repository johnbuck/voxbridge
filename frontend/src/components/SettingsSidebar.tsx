/**
 * Settings Sidebar Navigation
 */

import { Link, useLocation } from 'wouter';
import { cn } from '@/lib/utils';
import { Brain, Mic, Volume2, Plug, Database, User } from 'lucide-react';

const settingsItems = [
  { href: '/settings/account', label: 'Account', icon: User },
  { href: '/settings/llm-providers', label: 'LLM Providers', icon: Brain },
  { href: '/settings/memory', label: 'Memory', icon: Brain },
  { href: '/settings/whisperx', label: 'WhisperX STT', icon: Mic },
  { href: '/settings/chatterbox', label: 'Chatterbox TTS', icon: Volume2 },
  { href: '/settings/embeddings', label: 'Embeddings', icon: Database },
  { href: '/settings/plugins', label: 'Plugins', icon: Plug },
];

export function SettingsSidebar() {
  const [location] = useLocation();

  return (
    <nav className="space-y-1">
      <Link href="/settings">
        <a className={cn(
          "block px-4 py-2 rounded-lg text-sm font-medium transition-colors",
          location === '/settings'
            ? "bg-primary text-primary-foreground"
            : "hover:bg-muted"
        )}>
          Overview
        </a>
      </Link>

      {settingsItems.map((item) => {
        const Icon = item.icon;
        const isActive = location === item.href;

        return (
          <Link key={item.href} href={item.href}>
            <a className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
              isActive
                ? "bg-primary text-primary-foreground"
                : "hover:bg-muted"
            )}>
              <Icon className="h-4 w-4" />
              {item.label}
            </a>
          </Link>
        );
      })}
    </nav>
  );
}
