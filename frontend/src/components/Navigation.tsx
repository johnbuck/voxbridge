import { Link, useLocation } from 'wouter';
import { Home, Bot, Mic, Volume2, MessageSquare, Brain, Plug } from 'lucide-react';
import { cn } from '../lib/utils';

export default function Navigation() {
  const [location] = useLocation();

  const navItems = [
    {
      path: '/',
      label: 'Voxbridge',
      icon: Home,
      description: 'Main Dashboard - Status & Conversation'
    },
    {
      path: '/agents',
      label: 'Agents',
      icon: Brain,
      description: 'Manage AI Agents'
    },
    {
      path: '/plugins',
      label: 'Plugins',
      icon: Plug,
      description: 'Plugin Management & Monitoring'
    },
    {
      path: '/voice-chat',
      label: 'Voice Chat',
      icon: MessageSquare,
      description: 'Web Voice Chat Interface'
    },
    {
      path: '/discord-bot',
      label: 'Discord Bot',
      icon: Bot,
      description: 'Discord Bot Controls & Settings'
    },
    {
      path: '/whisperx',
      label: 'WhisperX',
      icon: Mic,
      description: 'Speech-to-Text Service'
    },
    {
      path: '/chatterbox-tts',
      label: 'Chatterbox TTS',
      icon: Volume2,
      description: 'Text-to-Speech Settings'
    }
  ];

  return (
    <nav className="w-full">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-center">
          <div className="flex items-center space-x-1 p-1 bg-muted rounded-lg">
            {navItems.map((item) => (
              <Link key={item.path} href={item.path}>
                <div
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 cursor-pointer",
                    "hover:bg-background hover:text-foreground",
                    location === item.path
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground"
                  )}
                  title={item.description}
                >
                  <item.icon className="w-4 h-4" />
                  <span>{item.label}</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </nav>
  );
}
