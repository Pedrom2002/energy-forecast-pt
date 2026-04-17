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
        className={`min-w-[32px] min-h-[32px] px-2 rounded-md text-[11px] font-mono font-semibold uppercase tracking-wider cursor-pointer transition-colors
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-offset-1 focus-visible:ring-offset-[#05080f]
          ${active
            ? 'bg-primary-500/15 text-primary-300 ring-1 ring-primary-400/30'
            : 'text-text-muted hover:text-text-primary hover:bg-white/[0.05]'
          }`}
      >
        {label}
      </button>
    );
  };

  return (
    <div
      className="inline-flex items-center gap-0.5 h-9 px-1 rounded-lg border border-border bg-surface-dim"
      role="group"
      aria-label={t('lang.switchAria')}
    >
      <Languages className="w-3.5 h-3.5 text-text-muted ml-1 mr-0.5" aria-hidden="true" />
      {btn('en', t('lang.en'), t('lang.english'))}
      {btn('pt', t('lang.pt'), t('lang.portuguese'))}
    </div>
  );
}
