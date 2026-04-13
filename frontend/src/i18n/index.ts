import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import en from './locales/en.json';
import pt from './locales/pt.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, pt: { translation: pt } },
    fallbackLng: 'en',
    supportedLngs: ['en', 'pt'],
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'lang',
    },
  });

/** Map current i18n language to a BCP-47 locale string for Intl APIs. */
export function formatLocale(): string {
  const lang = (i18n.language || 'en').toLowerCase();
  if (lang.startsWith('pt')) return 'pt-PT';
  return 'en-GB';
}

export default i18n;
