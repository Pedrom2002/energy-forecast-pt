import { motion, useReducedMotion } from 'motion/react';
import type { ReactNode } from 'react';

export interface GlassCardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}

const baseClasses =
  'bg-white/60 dark:bg-surface-bright/60 backdrop-blur-xl border border-white/20 dark:border-border/50 rounded-2xl shadow-sm hover:shadow-md transition-shadow';

export function GlassCard({ children, className, hover = false }: GlassCardProps) {
  const prefersReducedMotion = useReducedMotion();
  const mergedClass = className ? `${baseClasses} ${className}` : baseClasses;

  if (!hover || prefersReducedMotion) {
    return <div className={mergedClass}>{children}</div>;
  }

  return (
    <motion.div
      className={mergedClass}
      whileHover={{ y: -2, transition: { duration: 0.2 } }}
    >
      {children}
    </motion.div>
  );
}
