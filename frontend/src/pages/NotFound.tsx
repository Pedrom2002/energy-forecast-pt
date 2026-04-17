import { Link } from 'react-router-dom';
import { Home, ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] animate-fade-in-up">
      <div className="text-center">
        <p className="font-display text-8xl font-semibold tabular-nums leading-none text-gradient-signal tracking-tight">
          404
        </p>
        <h1 className="font-display text-2xl font-semibold text-text-primary mt-4 tracking-tight">
          {t('notFound.title')}
        </h1>
        <p className="text-sm text-text-secondary mt-3 max-w-sm mx-auto">
          {t('notFound.body')}
        </p>
        <div className="flex items-center justify-center gap-3 mt-7">
          <button
            type="button"
            onClick={() => window.history.back()}
            className="inline-flex items-center gap-2 text-sm font-medium text-text-secondary hover:text-text-primary
              border border-border hover:border-border-strong hover:bg-white/[0.04] min-h-[44px] px-4 rounded-lg
              transition-colors cursor-pointer
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
          >
            <ArrowLeft className="w-4 h-4" aria-hidden="true" />
            {t('notFound.back')}
          </button>
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm font-semibold
              bg-primary-500 hover:bg-primary-400 text-[#05080f]
              min-h-[44px] px-5 rounded-lg transition-colors
              shadow-[0_0_18px_rgba(34,211,238,0.35)] hover:shadow-[0_0_24px_rgba(34,211,238,0.5)]
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[#05080f]"
          >
            <Home className="w-4 h-4" aria-hidden="true" />
            {t('notFound.home')}
          </Link>
        </div>
      </div>
    </div>
  );
}
