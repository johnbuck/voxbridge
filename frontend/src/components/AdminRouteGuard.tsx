/**
 * Admin Route Guard
 * Temporary warning banner for admin routes until RBAC is implemented
 */

import { Card, CardContent } from '@/components/ui/card';
import { AlertTriangle } from 'lucide-react';

interface AdminRouteGuardProps {
  children: React.ReactNode;
}

export function AdminRouteGuard({ children }: AdminRouteGuardProps) {
  return (
    <div className="min-h-screen bg-page-background">
      {/* Warning Banner - No RBAC Yet */}
      <div className="container mx-auto px-4 pt-6">
        <Card className="border-yellow-500/50 bg-yellow-500/10">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
              <div className="space-y-2">
                <p className="text-sm font-medium text-yellow-600">
                  Warning: Admin Access - RBAC Not Implemented
                </p>
                <p className="text-xs text-yellow-600/90">
                  This admin panel is currently accessible to all users. Role-Based Access Control
                  (RBAC) has not been implemented yet. In production, these pages should be
                  restricted to administrator users only. This warning will be removed once
                  authentication and authorization are implemented.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Admin Content */}
      {children}
    </div>
  );
}
