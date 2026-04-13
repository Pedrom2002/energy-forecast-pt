import { Link } from 'react-router-dom';
import { Home, ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] animate-fade-in-up">
      <div className="text-center">
        <p className="text-7xl font-bold text-primary-200 tabular-nums">404</p>
        <h1 className="text-2xl font-bold text-text-primary mt-4">{t('notFound.title')}</h1>
        <p className="text-sm text-text-secondary mt-2 max-w-sm mx-auto">
          {t('notFound.body')}
        </p>
        <div className="flex items-center justify-center gap-3 mt-6">
          <button
            type="button"
            onClick={() => window.history.back()}
            className="inline-flex items-center gap-2 text-sm font-medium text-text-secondary hover:text-text-primary
              border border-border min-h-[44px] px-4 rounded-lg transition-colors cursor-pointer
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          >
            <ArrowLeft className="w-4 h-4" aria-hidden="true" />
            {t('notFound.back')}
          </button>
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm font-medium bg-primary-600 hover:bg-primary-700
              text-white min-h-[44px] px-5 rounded-lg transition-colors shadow-sm
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
          >
            <Home className="w-4 h-4" aria-hidden="true" />
            {t('notFound.home')}
          </Link>
        </div>
      </div>
    </div>
  );
}
