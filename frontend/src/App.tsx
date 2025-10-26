/**
 * VoxBridge Frontend App
 * Main application entry point
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Route, Switch } from 'wouter';
import { ThemeProvider } from '@/components/theme-provider';
import Header from '@/components/Header';
import { VoxbridgePage } from '@/pages/VoxbridgePage';
import { DiscordBotPage } from '@/pages/DiscordBotPage';
import { WhisperXPage } from '@/pages/WhisperXPage';
import { ChatterboxTTSPage } from '@/pages/ChatterboxTTSPage';
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
                <Route path="/" component={VoxbridgePage} />
                <Route path="/discord-bot" component={DiscordBotPage} />
                <Route path="/whisperx" component={WhisperXPage} />
                <Route path="/chatterbox-tts" component={ChatterboxTTSPage} />
                <Route>
                  {/* 404 Route */}
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
