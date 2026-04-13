import { useTranslation } from 'react-i18next';
import { Languages } from 'lucide-react';

export default function LanguageToggle() {
  const { i18n, t } = useTranslation();
  const current = (i18n.language || 'en').toLowerCase().startsWith('pt') ? 'pt' : 'en';

  const change = (lng: 'en' | 'pt') => {
    if (lng !== current) void i18n.changeLanguage(lng);
  };

  const btn = (lng: 'en' | 'pt', label: string, fullLabel: string) => {
    const active = current === lng;
    return (
      <button
        type="button"
        onClick={() => change(lng)}
        aria-pressed={active}
        aria-label={fullLabel}
        title={fullLabel}
        className={`min-w-[36px] min-h-[36px] px-2 rounded-md text-xs font-semibold cursor-pointer transition-colors
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2
          ${active
            ? 'bg-primary-600 text-white'
            : 'text-text-secondary hover:text-primary-600 hover:bg-surface-bright'
          }`}
      >
        {label}
      </button>
    );
  };

  return (
    <div
      className="inline-flex items-center gap-1 min-h-[44px] px-1.5 rounded-lg border border-border bg-surface"
      role="group"
      aria-label={t('lang.switchAria')}
    >
      <Languages className="w-3.5 h-3.5 text-text-muted ml-1 mr-0.5" aria-hidden="true" />
      {btn('en', t('lang.en'), t('lang.english'))}
      {btn('pt', t('lang.pt'), t('lang.portuguese'))}
    </div>
  );
}
