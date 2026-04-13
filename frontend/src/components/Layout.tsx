import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Zap,
  TrendingUp,
  Activity,
  Menu,
  X,
  Sun,
  Moon,
  Github,
  Linkedin,
  BookOpen,
} from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useTheme } from '../hooks/useTheme';
import LanguageToggle from './LanguageToggle';

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { toggle, isDark } = useTheme();
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const [apiOnline, setApiOnline] = useState(false);
  const prefersReducedMotion = useReducedMotion();
  const { t } = useTranslation();

  const NAV_ITEMS = [
    { to: '/', icon: LayoutDashboard, label: t('nav.dashboard') },
    { to: '/predict', icon: Zap, label: t('nav.predict') },
    { to: '/forecast', icon: TrendingUp, label: t('nav.forecast') },
    { to: '/monitoring', icon: Activity, label: t('nav.monitoring') },
  ];

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const base = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';
        const res = await fetch(`${base}/health`, { method: 'GET' });
        if (!cancelled) setApiOnline(res.ok);
      } catch {
        if (!cancelled) setApiOnline(false);
      }
    };
    check();
    const id = setInterval(check, 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    mainRef.current?.focus({ preventScroll: true });
  }, [location.pathname]);

  const isNavActive = (to: string) =>
    location.pathname === to || (to !== '/' && location.pathname.startsWith(to));

  return (
    <div className="flex flex-col h-dvh overflow-hidden">
      <div className="flex flex-1 min-h-0">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-2 focus:left-2 focus:bg-primary-600 focus:text-white focus:px-4 focus:py-2 focus:rounded-lg focus:text-sm focus:font-medium focus:outline-none focus:ring-2 focus:ring-primary-300"
      >
        {t('nav.skipToMain')}
      </a>

      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 lg:hidden animate-fade-in"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        role="navigation"
        aria-label={t('nav.mainNav')}
        className={`
          fixed lg:static inset-y-0 left-0 z-50
          w-64 bg-gradient-to-b from-surface to-surface-subtle dark:from-surface dark:to-background
          border-r border-border backdrop-blur-xl
          transform transition-transform duration-250 ease-[cubic-bezier(0.16,1,0.3,1)]
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
          flex flex-col
        `}
      >
        <div className="h-16 flex items-center gap-3 px-6 border-b border-border">
          <div className="w-9 h-9 rounded-xl bg-primary-500 flex items-center justify-center shadow-sm" aria-hidden="true">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div>
            <span className="text-sm font-bold text-text-primary tracking-tight">Energy Forecast</span>
            <p className="text-[11px] font-medium text-primary-500">{t('layout.subtitle')}</p>
          </div>
        </div>

        <nav className="flex-1 py-4 px-3 overflow-y-auto" aria-label={t('nav.menu')}>
          <p className="px-3 pb-2 text-xs uppercase tracking-wider text-text-muted font-medium">
            {t('nav.menu')}
          </p>
          <div className="relative space-y-1">
            {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
              const active = isNavActive(to);
              return (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  onClick={() => setSidebarOpen(false)}
                  className={`relative group flex items-center gap-3 px-3 min-h-[44px] rounded-lg text-sm font-medium
                    transition-colors duration-150
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2
                    ${active
                      ? 'text-primary-700 dark:text-primary-300'
                      : 'text-text-secondary hover:bg-surface-bright hover:text-text-primary'
                    }`}
                >
                  {active && (
                    prefersReducedMotion ? (
                      <span
                        className="absolute inset-0 bg-primary-100 dark:bg-primary-900/40 rounded-lg"
                        aria-hidden="true"
                      />
                    ) : (
                      <motion.div
                        layoutId="active-nav"
                        className="absolute inset-0 bg-primary-100 dark:bg-primary-900/40 rounded-lg"
                        transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                        aria-hidden="true"
                      />
                    )
                  )}
                  <div className={`relative z-10 w-8 h-8 rounded-lg flex items-center justify-center transition-colors duration-150 ${
                    active ? 'bg-primary-200/60 dark:bg-primary-800/50' : 'group-hover:bg-surface-bright'
                  }`}>
                    <Icon className="w-[18px] h-[18px] shrink-0" aria-hidden="true" />
                  </div>
                  <span className="relative z-10">{label}</span>
                </NavLink>
              );
            })}
          </div>
        </nav>

      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header
          className="h-14 bg-white/70 dark:bg-surface-bright/70 backdrop-blur-xl backdrop-saturate-150
            border-b border-white/20 dark:border-border/60
            shadow-[0_1px_0_rgba(255,255,255,0.05)_inset,0_4px_16px_rgba(0,0,0,0.03)]
            flex items-center px-4 sm:px-6 shrink-0 sticky top-0 z-30"
        >
          <button
            type="button"
            className="lg:hidden mr-3 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-lg hover:bg-surface-bright cursor-pointer
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 transition-colors"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label={sidebarOpen ? t('nav.closeMenu') : t('nav.openMenu')}
            aria-expanded={sidebarOpen}
          >
            {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          <div className="flex-1" />
          <div className="flex items-center gap-2 text-xs text-text-muted" aria-live="polite">
            <span className="w-2 h-2 rounded-full bg-energy-green animate-pulse" aria-hidden="true" />
            <span className="hidden sm:inline">{t('layout.poweredBy')}</span>
            <span className="sm:hidden">{t('layout.poweredByShort')}</span>
          </div>
        </header>

        <main
          ref={mainRef}
          id="main-content"
          className="flex-1 overflow-y-auto p-4 sm:p-6"
          role="main"
          tabIndex={-1}
        >
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: prefersReducedMotion ? 0 : -8 }}
              transition={{
                duration: prefersReducedMotion ? 0.1 : 0.25,
                ease: [0.22, 1, 0.36, 1],
              }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      </div>

      <footer
        className="shrink-0 border-t border-border-subtle bg-surface/60 backdrop-blur-sm
          px-4 py-3 lg:px-6
          flex flex-col lg:flex-row lg:items-center gap-3 lg:gap-4
          text-xs text-text-secondary"
        aria-label={t('layout.footerLabel')}
      >
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>
              {t('footer.builtBy')}{' '}
              <strong className="font-semibold text-primary-700 dark:text-primary-400">
                Pedro Marques
              </strong>
            </span>
            <span className="text-text-muted">{t('footer.version')}</span>
          </div>

          <div className="hidden lg:block flex-1" aria-hidden="true" />

          <nav
            className="flex items-center gap-1"
            aria-label={t('layout.externalLinks')}
          >
            <a
              href="https://github.com/Pedrom2002/energy-forecast-pt"
              target="_blank"
              rel="noopener noreferrer"
              title="GitHub"
              aria-label={t('layout.openGithub')}
              className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] rounded-lg
                text-text-secondary hover:text-primary-600 transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            >
              <Github className="w-4 h-4" aria-hidden="true" />
            </a>
            <a
              href="https://www.linkedin.com/in/pedro-marques-056baa366/"
              target="_blank"
              rel="noopener noreferrer"
              title="LinkedIn"
              aria-label={t('layout.openLinkedin')}
              className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] rounded-lg
                text-text-secondary hover:text-primary-600 transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            >
              <Linkedin className="w-4 h-4" aria-hidden="true" />
            </a>
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              title={t('layout.apiDocs')}
              aria-label={t('layout.openDocs')}
              className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] rounded-lg
                text-text-secondary hover:text-primary-600 transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            >
              <BookOpen className="w-4 h-4" aria-hidden="true" />
            </a>
          </nav>

          <div className="flex items-center gap-3 flex-wrap">
            <LanguageToggle />
            <button
              type="button"
              onClick={toggle}
              className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] rounded-lg
                text-text-secondary hover:text-primary-600 transition-colors cursor-pointer
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
              aria-label={isDark ? t('common.lightTheme') : t('common.darkTheme')}
              title={isDark ? t('common.lightTheme') : t('common.darkTheme')}
            >
              {isDark ? <Sun className="w-4 h-4" aria-hidden="true" /> : <Moon className="w-4 h-4" aria-hidden="true" />}
            </button>
            <div
              className="flex items-center gap-2"
              aria-live="polite"
              title={apiOnline ? t('layout.apiOnline') : t('layout.apiOffline')}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  apiOnline ? 'bg-energy-green animate-pulse' : 'bg-text-muted'
                }`}
                aria-hidden="true"
              />
              <span className="text-[11px] text-text-muted">
                API {apiOnline ? t('common.online') : t('common.offline')}
              </span>
            </div>
        </div>
      </footer>
    </div>
  );
}
