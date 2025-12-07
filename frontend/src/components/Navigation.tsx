import { useState } from 'react';
import { Link, useLocation } from 'wouter';
import { Home, Brain, Database, Settings, Shield, Menu, X, BookOpen } from 'lucide-react';
import { cn } from '../lib/utils';

export default function Navigation() {
  const [location] = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = [
    {
      path: '/',
      label: 'Voxbridge',
      icon: Home,
      description: 'Main Dashboard - Analytics, Voice Chat & Conversation'
    },
    {
      path: '/agents',
      label: 'Agents',
      icon: Brain,
      description: 'Manage AI Agents'
    },
    {
      path: '/memory',
      label: 'Memory',
      icon: Database,
      description: 'Manage User Facts & Memory Settings'
    },
    {
      path: '/knowledge',
      label: 'Knowledge',
      icon: BookOpen,
      description: 'RAG Collections & Documents'
    },
    {
      path: '/settings',
      label: 'Settings',
      icon: Settings,
      description: 'Configure Services & Integrations'
    },
    {
      path: '/admin',
      label: 'Admin',
      icon: Shield,
      description: 'Admin Panel - System Configuration'
    }
  ];

  return (
    <nav className="w-full">
      {/* Desktop Navigation */}
      <div className="hidden md:flex items-center justify-center">
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

      {/* Mobile Navigation */}
      <div className="md:hidden">
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-2 rounded-md hover:bg-muted"
          aria-label="Toggle menu"
        >
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>

        {/* Mobile Menu Dropdown */}
        {mobileMenuOpen && (
          <div className="absolute left-0 right-0 top-full bg-background border-b border-border shadow-lg z-50">
            <div className="flex flex-col p-2">
              {navItems.map((item) => (
                <Link key={item.path} href={item.path}>
                  <div
                    onClick={() => setMobileMenuOpen(false)}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3 rounded-md text-sm font-medium transition-all duration-200 cursor-pointer",
                      "hover:bg-muted",
                      location === item.path
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground"
                    )}
                  >
                    <item.icon className="w-5 h-5" />
                    <span>{item.label}</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}
