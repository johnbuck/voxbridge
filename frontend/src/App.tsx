/**
 * VoxBridge Frontend App
 * Main application entry point
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Route, Switch } from 'wouter';
import { ThemeProvider } from '@/components/theme-provider';
import { AuthProvider } from '@/contexts/AuthContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import Header from '@/components/Header';
import { VoxbridgePage } from '@/pages/VoxbridgePage';
import { AgentsPage } from '@/pages/AgentsPage';
import { MemoryPage } from '@/pages/MemoryPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { AdminPage } from '@/pages/AdminPage';
import { LoginPage } from '@/pages/LoginPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { ToastProvider } from '@/components/ui/toast';
import '@/styles/globals.css';

// Create React Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 1000, // Consider data stale after 1 second
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ThemeProvider defaultTheme="dark" storageKey="voxbridge-ui-theme">
          <ToastProvider>
            <div className="min-h-screen flex flex-col">
              {/* Header with Navigation */}
              <Header />

              {/* Main Content with Routing */}
              <main className="flex-1">
                <Switch>
                  {/* Public Routes */}
                  <Route path="/login" component={LoginPage} />
                  <Route path="/register" component={RegisterPage} />

                  {/* Protected Routes - Require Authentication */}
                  <Route path="/">
                    <ProtectedRoute>
                      <VoxbridgePage />
                    </ProtectedRoute>
                  </Route>

                  <Route path="/agents">
                    <ProtectedRoute>
                      <AgentsPage />
                    </ProtectedRoute>
                  </Route>

                  <Route path="/memory">
                    <ProtectedRoute>
                      <MemoryPage />
                    </ProtectedRoute>
                  </Route>

                  {/* Admin Routes - Require Admin Role */}
                  <Route path="/admin">
                    <ProtectedRoute requireAdmin>
                      <AdminPage />
                    </ProtectedRoute>
                  </Route>
                  <Route path="/admin/memory-policy">
                    <ProtectedRoute requireAdmin>
                      <AdminPage />
                    </ProtectedRoute>
                  </Route>

                  {/* Settings Routes - Require Authentication */}
                  <Route path="/settings">
                    <ProtectedRoute>
                      <SettingsPage />
                    </ProtectedRoute>
                  </Route>
                  <Route path="/settings/llm-providers">
                    <ProtectedRoute>
                      <SettingsPage />
                    </ProtectedRoute>
                  </Route>
                  <Route path="/settings/memory">
                    <ProtectedRoute>
                      <SettingsPage />
                    </ProtectedRoute>
                  </Route>
                  <Route path="/settings/whisperx">
                    <ProtectedRoute>
                      <SettingsPage />
                    </ProtectedRoute>
                  </Route>
                  <Route path="/settings/chatterbox">
                    <ProtectedRoute>
                      <SettingsPage />
                    </ProtectedRoute>
                  </Route>
                  <Route path="/settings/embeddings">
                    <ProtectedRoute>
                      <SettingsPage />
                    </ProtectedRoute>
                  </Route>
                  <Route path="/settings/plugins">
                    <ProtectedRoute>
                      <SettingsPage />
                    </ProtectedRoute>
                  </Route>

                  {/* 404 Route */}
                  <Route>
                    <div className="container mx-auto px-4 py-8 text-center">
                      <h2 className="text-2xl font-bold mb-2">Page Not Found</h2>
                      <p className="text-muted-foreground">The page you're looking for doesn't exist.</p>
                    </div>
                  </Route>
                </Switch>
              </main>
            </div>
          </ToastProvider>
        </ThemeProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
