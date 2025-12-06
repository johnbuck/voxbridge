/**
 * Admin Panel Page
 * Main admin page with sidebar navigation and overview dashboard
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AdminSidebar } from '@/components/AdminSidebar';
import { AdminRouteGuard } from '@/components/AdminRouteGuard';
import { Link, useLocation } from 'wouter';
import { Shield, Users, Settings as SettingsIcon, Lock } from 'lucide-react';
import { AdminMemorySettingsPage } from './settings/AdminMemorySettingsPage';
import { AdminUsersPage } from './settings/AdminUsersPage';

/**
 * Overview Dashboard Component
 * Displays clickable cards for each admin feature
 */
function AdminOverview() {
  return (
    <>
      <div className="mb-6">
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <Shield className="h-8 w-8" />
          Admin Panel
        </h1>
        <p className="text-muted-foreground mt-2">
          System-wide configuration and management
        </p>
      </div>

      {/* Admin Feature Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Memory Policy Card - Active */}
        <Link href="/admin/memory-policy">
          <Card className="hover:border-primary/50 cursor-pointer transition-colors">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-5 w-5" />
                Memory Policy
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                System-wide control over agent-specific memory capabilities
              </p>
            </CardContent>
          </Card>
        </Link>

        {/* User Management Card - Active */}
        <Link href="/admin/users">
          <Card className="hover:border-primary/50 cursor-pointer transition-colors">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                User Management
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Manage users, roles, and permissions
              </p>
            </CardContent>
          </Card>
        </Link>

        {/* System Settings Card - Placeholder */}
        <Card className="opacity-50 cursor-not-allowed">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <SettingsIcon className="h-5 w-5" />
              System Settings
              <span className="ml-auto text-xs font-normal text-muted-foreground">Coming Soon</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Configure global system settings and performance
            </p>
          </CardContent>
        </Card>

        {/* Security Card - Placeholder */}
        <Card className="opacity-50 cursor-not-allowed">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lock className="h-5 w-5" />
              Security & Audit Logs
              <span className="ml-auto text-xs font-normal text-muted-foreground">Coming Soon</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Security settings, audit logs, and access monitoring
            </p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

export function AdminPage() {
  const [location] = useLocation();

  // Determine which content to show based on location
  let content;
  if (location === '/admin') {
    content = <AdminOverview />;
  } else if (location === '/admin/memory-policy') {
    content = <AdminMemorySettingsPage />;
  } else if (location === '/admin/users') {
    content = <AdminUsersPage />;
  }

  return (
    <AdminRouteGuard>
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex gap-6">
          {/* Sidebar Navigation - Hidden on mobile, visible on desktop */}
          <aside className="hidden md:block w-64 flex-shrink-0">
            <AdminSidebar />
          </aside>

          {/* Main Content Area */}
          <div className="flex-1 min-w-0">
            {content}
          </div>
        </div>
      </div>
    </AdminRouteGuard>
  );
}
