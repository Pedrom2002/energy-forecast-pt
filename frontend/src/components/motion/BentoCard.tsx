import { motion, useReducedMotion } from 'motion/react';
import type { ReactNode } from 'react';

export type BentoSize = 'sm' | 'md' | 'lg' | 'xl' | 'wide' | 'tall';

export interface BentoCardProps {
  children: ReactNode;
  className?: string;
  size?: BentoSize;
  /**
   * If true, overlays a subtle cyan glow gradient on the card background.
   * Use sparingly — reserve for hero/emphasis tiles.
   */
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

const baseClasses = 'glass-card relative overflow-hidden p-5 sm:p-6';

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
          className="pointer-events-none absolute inset-0
            bg-[radial-gradient(ellipse_100%_60%_at_0%_0%,rgba(34,211,238,0.08),transparent_60%)]"
        />
      )}
      <div className="relative h-full">{children}</div>
    </>
  );

  if (prefersReducedMotion) {
    return <div className={mergedClass}>{content}</div>;
  }

  return (
    <motion.div
      className={mergedClass}
      whileHover={{ y: -2, transition: { type: 'spring', stiffness: 320, damping: 22 } }}
    >
      {content}
    </motion.div>
  );
}
