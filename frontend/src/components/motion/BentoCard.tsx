import { motion, useReducedMotion } from 'motion/react';
import type { ReactNode } from 'react';

export type BentoSize = 'sm' | 'md' | 'lg' | 'xl' | 'wide' | 'tall';

export interface BentoCardProps {
  children: ReactNode;
  className?: string;
  size?: BentoSize;
  gradient?: boolean;
}

const sizeClasses: Record<BentoSize, string> = {
  sm: 'col-span-1 row-span-1',
  md: 'col-span-1 row-span-2',
  lg: 'col-span-2 row-span-1',
  xl: 'col-span-2 row-span-2',
  wide: 'col-span-3 row-span-1',
  tall: 'col-span-1 row-span-3',
};

const baseClasses =
  'relative overflow-hidden rounded-2xl p-6 bg-surface dark:bg-surface-subtle border border-border hover:border-primary-300 dark:hover:border-primary-700 transition-all duration-300';

export function BentoCard({
  children,
  className,
  size = 'sm',
  gradient = false,
}: BentoCardProps) {
  const prefersReducedMotion = useReducedMotion();
  const mergedClass = [baseClasses, sizeClasses[size], className].filter(Boolean).join(' ');

  const content = (
    <>
      {gradient && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary-50/60 via-transparent to-transparent"
        />
      )}
      <div className="relative">{children}</div>
    </>
  );

  if (prefersReducedMotion) {
    return <div className={mergedClass}>{content}</div>;
  }

  return (
    <motion.div
      className={mergedClass}
      whileHover={{ y: -3, transition: { type: 'spring', stiffness: 300 } }}
    >
      {content}
    </motion.div>
  );
}
