import { type ReactElement } from 'react';
import { render, type RenderOptions } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/**
 * Test renderer that wraps a component with the providers the real app
 * uses (React Router + React Query). The QueryClient is scoped to each
 * render so tests don't share cached query state.
 */
export function renderWithProviders(
  ui: ReactElement,
  {
    route = '/',
    ...options
  }: RenderOptions & { route?: string } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
    options,
  );
}
