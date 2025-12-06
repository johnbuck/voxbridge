/**
 * Admin Route Guard
 * Wrapper for admin routes - RBAC is now implemented via JWT auth
 */

interface AdminRouteGuardProps {
  children: React.ReactNode;
}

export function AdminRouteGuard({ children }: AdminRouteGuardProps) {
  // RBAC is now enforced via:
  // 1. ProtectedRoute with requireAdmin prop (frontend)
  // 2. require_admin dependency (backend API)
  return (
    <div className="min-h-screen bg-page-background">
      {children}
    </div>
  );
}
