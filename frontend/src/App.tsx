/**
 * VoxBridge Frontend App
 * Main application entry point
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Dashboard } from '@/pages/Dashboard';
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
      <div className="dark">
        <Dashboard />
      </div>
    </QueryClientProvider>
  );
}

export default App;
