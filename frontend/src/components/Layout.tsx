import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Zap,
  TrendingUp,
  Activity,
  Github,
  Linkedin,
  BookOpen,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import LanguageToggle from './LanguageToggle';

export default function Layout() {
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const [apiOnline, setApiOnline] = useState(false);
  const prefersReducedMotion = useReducedMotion();
  const { t } = useTranslation();

  const NAV_ITEMS = [
    { to: '/', icon: LayoutDashboard, label: t('nav.dashboard'), short: t('nav.dashboardShort') },
    { to: '/predict', icon: Zap, label: t('nav.predict'), short: t('nav.predictShort') },
    { to: '/forecast', icon: TrendingUp, label: t('nav.forecast'), short: t('nav.forecastShort') },
    { to: '/monitoring', icon: Activity, label: t('nav.monitoring'), short: t('nav.monitoringShort') },
  ];

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const envBase = (import.meta as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL;
        const base = envBase !== undefined ? envBase.replace(/\/$/, '') : '/api';
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
    <div className="min-h-dvh flex flex-col lg:flex-row">
      {/* Skip link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-2 focus:left-2
          focus:bg-primary-500 focus:text-[#05080f] focus:px-4 focus:py-2 focus:rounded-lg
          focus:text-sm focus:font-medium focus:outline-none focus:ring-2 focus:ring-primary-300"
      >
        {t('nav.skipToMain')}
      </a>

      {/* ─── Desktop sidebar (lg+) ─── */}
      <aside
        role="navigation"
        aria-label={t('nav.mainNav')}
        className="hidden lg:flex lg:flex-col w-[244px] shrink-0 sticky top-0 h-dvh
          border-r border-border bg-[#070c18]/80 backdrop-blur-xl"
      >
        <div className="h-16 flex items-center gap-3 px-6 border-b border-border-subtle">
          <div
            className="w-9 h-9 rounded-lg bg-gradient-to-br from-primary-400 to-primary-600
              flex items-center justify-center shadow-[0_0_12px_rgba(34,211,238,0.35)]"
            aria-hidden="true"
          >
            <Zap className="w-[18px] h-[18px] text-[#05080f]" strokeWidth={2.5} />
          </div>
          <div className="min-w-0">
            <span className="font-display text-sm font-semibold tracking-tight block leading-tight">
              Energy Forecast
            </span>
            <p className="text-[11px] font-mono text-primary-400 tracking-wider uppercase">
              {t('layout.subtitle')}
            </p>
          </div>
        </div>

        <nav className="flex-1 py-6 px-3 overflow-y-auto" aria-label={t('nav.menu')}>
          <p className="px-3 pb-3 text-[10px] uppercase tracking-[0.14em] text-text-muted font-semibold font-mono">
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
                  className={`relative group flex items-center gap-3 px-3 h-11 rounded-lg text-sm font-medium
                    transition-colors duration-150
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400
                    ${active ? 'text-primary-300' : 'text-text-secondary hover:text-text-primary hover:bg-white/[0.03]'}`}
                >
                  {active && (
                    prefersReducedMotion ? (
                      <span
                        className="absolute inset-0 rounded-lg bg-primary-500/10 border border-primary-400/25
                          shadow-[inset_0_1px_0_rgba(34,211,238,0.15)]"
                        aria-hidden="true"
                      />
                    ) : (
                      <motion.div
                        layoutId="active-nav-desktop"
                        className="absolute inset-0 rounded-lg bg-primary-500/10 border border-primary-400/25
                          shadow-[inset_0_1px_0_rgba(34,211,238,0.15)]"
                        transition={{ type: 'spring', stiffness: 420, damping: 32 }}
                        aria-hidden="true"
                      />
                    )
                  )}
                  <Icon
                    className={`relative z-10 w-[18px] h-[18px] shrink-0 ${active ? 'text-primary-400' : ''}`}
                    aria-hidden="true"
                  />
                  <span className="relative z-10">{label}</span>
                  {active && (
                    <span
                      className="relative z-10 ml-auto w-1.5 h-1.5 rounded-full bg-primary-400
                        shadow-[0_0_8px_rgba(34,211,238,0.8)]"
                      aria-hidden="true"
                    />
                  )}
                </NavLink>
              );
            })}
          </div>
        </nav>

        {/* Sidebar footer: API status + lang + links */}
        <div className="border-t border-border-subtle px-4 py-3 space-y-3">
          <div
            className="flex items-center gap-2 text-xs text-text-secondary"
            title={apiOnline ? t('layout.apiOnline') : t('layout.apiOffline')}
            aria-live="polite"
          >
            <span className="relative flex items-center justify-center">
              <span
                className={`absolute inline-flex h-2 w-2 rounded-full ${apiOnline ? 'bg-energy-green' : 'bg-text-muted'} opacity-70 ${apiOnline ? 'animate-ping' : ''}`}
              />
              <span
                className={`relative inline-flex h-1.5 w-1.5 rounded-full ${apiOnline ? 'bg-energy-green' : 'bg-text-muted'}`}
              />
            </span>
            <span className="font-mono text-[11px] uppercase tracking-wider">
              API {apiOnline ? t('common.online') : t('common.offline')}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <LanguageToggle />
            <div className="flex items-center gap-0.5" role="group" aria-label={t('layout.externalLinks')}>
              <IconLink href="https://github.com/Pedrom2002/energy-forecast-pt" label="GitHub"><Github className="w-4 h-4" /></IconLink>
              <IconLink href="https://www.linkedin.com/in/pedro-marques-056baa366/" label="LinkedIn"><Linkedin className="w-4 h-4" /></IconLink>
              <IconLink href="/docs" label={t('layout.apiDocs')}><BookOpen className="w-4 h-4" /></IconLink>
            </div>
          </div>
        </div>
      </aside>

      {/* ─── Main column (header + content + mobile bottom nav) ─── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar (mobile + desktop) */}
        <header
          className="h-14 sticky top-0 z-30 flex items-center gap-3 px-4 sm:px-6
            border-b border-border bg-[#05080f]/80 backdrop-blur-xl"
        >
          {/* Mobile logo */}
          <div className="flex items-center gap-2.5 lg:hidden">
            <div
              className="w-8 h-8 rounded-md bg-gradient-to-br from-primary-400 to-primary-600
                flex items-center justify-center shadow-[0_0_10px_rgba(34,211,238,0.3)]"
              aria-hidden="true"
            >
              <Zap className="w-4 h-4 text-[#05080f]" strokeWidth={2.5} />
            </div>
            <span className="font-display text-sm font-semibold tracking-tight">
              Energy Forecast
            </span>
          </div>

          <div className="flex-1" />

          {/* API live indicator (compact, desktop shows in sidebar too — here it's quick glance) */}
          <div
            className="flex items-center gap-2 text-xs text-text-secondary"
            aria-live="polite"
          >
            <span className="relative flex items-center justify-center">
              <span
                className={`absolute inline-flex h-2 w-2 rounded-full ${apiOnline ? 'bg-energy-green' : 'bg-text-muted'} opacity-70 ${apiOnline ? 'animate-ping' : ''}`}
                aria-hidden="true"
              />
              <span
                className={`relative inline-flex h-1.5 w-1.5 rounded-full ${apiOnline ? 'bg-energy-green' : 'bg-text-muted'}`}
                aria-hidden="true"
              />
            </span>
            <span className="hidden sm:inline font-mono text-[11px] uppercase tracking-wider">
              {apiOnline ? t('layout.apiOnline') : t('layout.apiOffline')}
            </span>
          </div>

          {/* Language toggle — mobile shows it here */}
          <div className="lg:hidden">
            <LanguageToggle />
          </div>
        </header>

        <main
          ref={mainRef}
          id="main-content"
          className="flex-1 px-4 sm:px-6 py-6 sm:py-8 pb-24 lg:pb-10 overflow-x-hidden"
          role="main"
          tabIndex={-1}
        >
          <div className="max-w-[1400px] mx-auto w-full">
            <AnimatePresence mode="wait">
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: prefersReducedMotion ? 0 : -6 }}
                transition={{
                  duration: prefersReducedMotion ? 0.08 : 0.22,
                  ease: [0.22, 1, 0.36, 1],
                }}
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </div>
        </main>

        {/* Desktop footer (single line) */}
        <footer
          className="hidden lg:flex shrink-0 items-center gap-3 px-6 py-3
            border-t border-border-subtle text-[11px] text-text-muted font-mono tracking-wider uppercase"
          aria-label={t('layout.footerLabel')}
        >
          <span>
            {t('footer.builtBy')}{' '}
            <strong className="text-primary-300 font-semibold tracking-wider">Pedro Marques</strong>
          </span>
          <span aria-hidden="true">·</span>
          <span>{t('footer.version')}</span>
        </footer>
      </div>

      {/* ─── Mobile bottom nav (< lg) ─── */}
      <nav
        className="lg:hidden fixed bottom-0 inset-x-0 z-40 safe-bottom
          border-t border-border bg-[#070c18]/92 backdrop-blur-xl"
        aria-label={t('nav.mainNav')}
      >
        <div className="grid grid-cols-4 h-16">
          {NAV_ITEMS.map(({ to, icon: Icon, short }) => {
            const active = isNavActive(to);
            return (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className="relative flex flex-col items-center justify-center gap-1
                  text-[11px] font-medium transition-colors duration-150
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-inset"
                aria-label={short}
              >
                {active && (
                  <span
                    className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-b-full
                      bg-primary-400 shadow-[0_0_8px_rgba(34,211,238,0.9)]"
                    aria-hidden="true"
                  />
                )}
                <Icon
                  className={`w-5 h-5 transition-colors ${active ? 'text-primary-400' : 'text-text-muted'}`}
                  aria-hidden="true"
                />
                <span className={active ? 'text-text-primary' : 'text-text-muted'}>
                  {short}
                </span>
              </NavLink>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

function IconLink({ href, label, children }: { href: string; label: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target={href.startsWith('http') ? '_blank' : undefined}
      rel={href.startsWith('http') ? 'noopener noreferrer' : undefined}
      title={label}
      aria-label={label}
      className="inline-flex items-center justify-center w-9 h-9 rounded-lg
        text-text-muted hover:text-primary-300 hover:bg-white/[0.03] transition-colors
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
    >
      {children}
    </a>
  );
}
