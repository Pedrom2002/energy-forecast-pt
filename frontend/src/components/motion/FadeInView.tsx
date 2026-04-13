import { motion, useInView, useReducedMotion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

export interface FadeInViewProps {
  children: ReactNode;
  className?: string;
  delay?: number;
  direction?: 'up' | 'down' | 'left' | 'right' | 'none';
  distance?: number;
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

export function FadeInView({
  children,
  className,
  delay = 0,
  direction = 'up',
  distance = 24,
  once = true,
}: FadeInViewProps) {
  const prefersReducedMotion = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once, amount: 0.05, margin: '-40px' });
  const [forceShow, setForceShow] = useState(false);

  // Safety fallback: if IntersectionObserver doesn't fire within 1.2s after mount,
  // reveal the content anyway so it never stays invisible (handles programmatic
  // scroll or unusual viewport scenarios).
  useEffect(() => {
    if (prefersReducedMotion) return;
    const t = window.setTimeout(() => setForceShow(true), 1200);
    return () => window.clearTimeout(t);
  }, [prefersReducedMotion]);

  if (prefersReducedMotion) {
    return <div className={className}>{children}</div>;
  }

  const visible = isInView || forceShow;
  const offset = getOffset(direction, distance);

  return (
    <motion.div
      ref={ref}
      className={className}
      initial={{ opacity: 0, x: offset.x, y: offset.y }}
      animate={visible ? { opacity: 1, x: 0, y: 0 } : undefined}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
