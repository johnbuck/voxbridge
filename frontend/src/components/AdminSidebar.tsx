/**
 * Admin Sidebar Navigation
 * Navigation for admin panel sections
 */

import { Link, useLocation } from 'wouter';
import { cn } from '@/lib/utils';
import { Shield } from 'lucide-react';

const adminItems = [
  { href: '/admin/memory-policy', label: 'Memory Policy', icon: Shield },
  // Future admin features (will require additional imports):
  // Users, Settings as SettingsIcon, Lock from lucide-react
  // { href: '/admin/users', label: 'User Management', icon: Users, disabled: true },
  // { href: '/admin/system', label: 'System Settings', icon: SettingsIcon, disabled: true },
  // { href: '/admin/security', label: 'Security', icon: Lock, disabled: true },
];

export function AdminSidebar() {
  const [location] = useLocation();

  return (
    <nav className="space-y-1">
      <Link href="/admin">
        <a className={cn(
          "block px-4 py-2 rounded-lg text-sm font-medium transition-colors",
          location === '/admin'
            ? "bg-primary text-primary-foreground"
            : "hover:bg-muted"
        )}>
          Overview
        </a>
      </Link>

      {adminItems.map((item) => {
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
