/**
 * VoxBridge Frontend App
 * Main application entry point
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Route, Switch } from 'wouter';
import { ThemeProvider } from '@/components/theme-provider';
import Header from '@/components/Header';
import { VoxbridgePage } from '@/pages/VoxbridgePage';
import { AgentsPage } from '@/pages/AgentsPage';
import { MemoryPage } from '@/pages/MemoryPage';
import { SettingsPage } from '@/pages/SettingsPage';
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
      <ThemeProvider defaultTheme="dark" storageKey="voxbridge-ui-theme">
        <ToastProvider>
          <div className="min-h-screen flex flex-col">
            {/* Header with Navigation */}
            <Header />

            {/* Main Content with Routing */}
            <main className="flex-1">
              <Switch>
                {/* VoxBridge Unified Interface - Analytics, Voice Chat, Conversation Management */}
                <Route path="/" component={VoxbridgePage} />

                {/* Agent Management */}
                <Route path="/agents" component={AgentsPage} />

                {/* Memory Management */}
                <Route path="/memory" component={MemoryPage} />

                {/* Settings Hub - all routes render SettingsPage which handles content internally */}
                <Route path="/settings" component={SettingsPage} />
                <Route path="/settings/llm-providers" component={SettingsPage} />
                <Route path="/settings/memory" component={SettingsPage} />
                <Route path="/settings/admin-policy" component={SettingsPage} />
                <Route path="/settings/whisperx" component={SettingsPage} />
                <Route path="/settings/chatterbox" component={SettingsPage} />
                <Route path="/settings/embeddings" component={SettingsPage} />
                <Route path="/settings/plugins" component={SettingsPage} />

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
    </QueryClientProvider>
  );
}

export default App;
