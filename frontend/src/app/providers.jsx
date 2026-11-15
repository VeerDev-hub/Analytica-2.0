import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeSync } from '../store/theme.js';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
  },
});

/** @param {{ children: import('react').ReactNode }} props */
export function AppProviders({ children }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeSync />
      {children}
    </QueryClientProvider>
  );
}
