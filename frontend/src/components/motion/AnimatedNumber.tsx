import { motion, useSpring, useTransform, useReducedMotion } from 'motion/react';
import { memo, useEffect } from 'react';

export interface AnimatedNumberProps {
  value: number;
  format?: (n: number) => string;
  duration?: number;
  className?: string;
}

function AnimatedNumberImpl({
  value,
  format = (n) => Math.round(n).toString(),
  className,
}: AnimatedNumberProps) {
  const prefersReducedMotion = useReducedMotion();
  const spring = useSpring(0, { stiffness: 100, damping: 20, mass: 1 });
  const display = useTransform(spring, (latest) => format(latest));

  useEffect(() => {
    if (prefersReducedMotion) {
      spring.jump(value);
    } else {
      spring.set(value);
    }
  }, [value, prefersReducedMotion, spring]);

  if (prefersReducedMotion) {
    return <span className={className}>{format(value)}</span>;
  }

  return <motion.span className={className}>{display}</motion.span>;
}

export const AnimatedNumber = memo(
  AnimatedNumberImpl,
  (prev, next) =>
    prev.value === next.value &&
    prev.className === next.className &&
    prev.format === next.format,
);
