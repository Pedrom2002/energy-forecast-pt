import { useEffect } from 'react';

/**
 * Sets document.title to "{page} · Energy Forecast PT" while mounted.
 * Restores the previous title on unmount.
 */
export function useDocumentTitle(page: string): void {
  useEffect(() => {
    const previous = document.title;
    document.title = `${page} · Energy Forecast PT`;
    return () => {
      document.title = previous;
    };
  }, [page]);
}
