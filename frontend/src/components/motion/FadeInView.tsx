import { motion, useReducedMotion } from 'motion/react';
import type { ReactNode } from 'react';

export interface FadeInViewProps {
  children: ReactNode;
  className?: string;
  delay?: number;
  direction?: 'up' | 'down' | 'left' | 'right' | 'none';
  distance?: number;
  /** Kept for API compatibility — currently animates on mount regardless. */
  once?: boolean;
}

function getOffset(direction: FadeInViewProps['direction'], distance: number) {
  switch (direction) {
    case 'up':
      return { x: 0, y: distance };
    case 'down':
      return { x: 0, y: -distance };
    case 'left':
      return { x: distance, y: 0 };
    case 'right':
      return { x: -distance, y: 0 };
    case 'none':
    default:
      return { x: 0, y: 0 };
  }
}

/**
 * Fade + slide-in wrapper that animates on mount.
 *
 * Previously used `whileInView` + IntersectionObserver, but it proved
 * unreliable under programmatic scroll, mobile Safari reloads, and some
 * viewport sizes — leaving content stuck at opacity 0.  Animating on mount
 * guarantees the content is always visible.  For the scroll-reveal feel,
 * callers pass a `delay` proportional to vertical position so sections
 * further down animate slightly later.
 */
export function FadeInView({
  children,
  className,
  delay = 0,
  direction = 'up',
  distance = 24,
}: FadeInViewProps) {
  const prefersReducedMotion = useReducedMotion();

  if (prefersReducedMotion) {
    return <div className={className}>{children}</div>;
  }

  const offset = getOffset(direction, distance);

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, x: offset.x, y: offset.y }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
