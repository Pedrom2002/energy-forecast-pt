import type { ReactNode } from 'react';

interface EmptyStateProps {
  illustration: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ illustration, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center animate-fade-in">
      <div className="mb-6 opacity-90">{illustration}</div>
      <h3 className="text-lg font-semibold text-text-primary mb-2">{title}</h3>
      {description && (
        <p className="text-sm text-text-secondary max-w-sm mb-4 leading-relaxed">{description}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
