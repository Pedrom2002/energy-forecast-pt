import { useRef, useCallback } from 'react';

/**
 * Returns a debounced version of the callback.
 * rule: debounce-throttle — prevent spam on high-frequency events
 */
export function useDebounce<T extends (...args: unknown[]) => void>(
  fn: T,
  delayMs = 500,
): T {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  return useCallback(
    (...args: unknown[]) => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => fn(...args), delayMs);
    },
    [fn, delayMs],
  ) as unknown as T;
}
