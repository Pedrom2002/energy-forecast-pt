import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Zap,
  Layers,
  TrendingUp,
  Activity,
  Brain,
  Menu,
  X,
  Sun,
  Moon,
  Github,
  Linkedin,
  BookOpen,
} from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import { useTheme } from '../hooks/useTheme';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/predict', icon: Zap, label: 'Previsão' },
  { to: '/batch', icon: Layers, label: 'Batch' },
  { to: '/forecast', icon: TrendingUp, label: 'Forecast' },
  { to: '/monitoring', icon: Activity, label: 'Monitoring' },
  { to: '/explain', icon: Brain, label: 'Explicabilidade' },
];

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { theme, toggle, isDark } = useTheme();
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const [apiOnline, setApiOnline] = useState(false);

  // Poll backend health (reuse same localhost:8000 assumption as sidebar)
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

  // Focus main content on route change — accessibility: focus-on-route-change
  useEffect(() => {
    mainRef.current?.focus({ preventScroll: true });
  }, [location.pathname]);

  return (
    <div className="flex min-h-dvh overflow-hidden">
      {/* Skip link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-2 focus:left-2 focus:bg-primary-600 focus:text-white focus:px-4 focus:py-2 focus:rounded-lg focus:text-sm focus:font-medium focus:outline-none focus:ring-2 focus:ring-primary-300"
      >
        Ir para conteúdo principal
      </a>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 lg:hidden animate-fade-in"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        role="navigation"
        aria-label="Navegacao principal"
        className={`
          fixed lg:static inset-y-0 left-0 z-50
          w-64 bg-surface border-r border-border
          transform transition-transform duration-250 ease-[cubic-bezier(0.16,1,0.3,1)]
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
          flex flex-col
        `}
      >
        {/* Logo — branded gradient */}
        <div className="h-16 flex items-center gap-3 px-6 border-b border-border relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-r from-primary-600/5 via-primary-400/3 to-transparent" aria-hidden="true" />
          <div className="relative w-9 h-9 rounded-xl bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center shadow-md" aria-hidden="true">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div className="relative">
            <span className="text-sm font-bold text-text-primary tracking-tight">Energy Forecast</span>
            <p className="text-[11px] font-medium text-primary-500">Portugal</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto" aria-label="Menu principal">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 min-h-[44px] rounded-lg text-sm font-medium
                transition-all duration-150
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2
                ${isActive
                  ? 'bg-primary-50 text-primary-700 shadow-xs'
                  : 'text-text-secondary hover:bg-surface-bright hover:text-text-primary'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors duration-150 ${
                    isActive ? 'bg-primary-100' : 'group-hover:bg-surface-bright'
                  }`}>
                    <Icon className="w-[18px] h-[18px] shrink-0" aria-hidden="true" />
                  </div>
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-14 bg-surface/80 backdrop-blur-md border-b border-border flex items-center px-4 sm:px-6 shrink-0 sticky top-0 z-30">
          <button
            type="button"
            className="lg:hidden mr-3 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-lg hover:bg-surface-bright cursor-pointer
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 transition-colors"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label={sidebarOpen ? 'Fechar menu' : 'Abrir menu'}
            aria-expanded={sidebarOpen}
          >
            {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          <div className="flex-1" />
          <div className="flex items-center gap-2 text-xs text-text-muted" aria-live="polite">
            <span className="w-2 h-2 rounded-full bg-energy-green animate-pulse" aria-hidden="true" />
            <span className="hidden sm:inline">Powered by CatBoost + Conformal Prediction</span>
            <span className="sm:hidden">CatBoost + CP</span>
          </div>
        </header>

        {/* Page content with transition */}
        <main
          ref={mainRef}
          id="main-content"
          className="flex-1 overflow-y-auto p-4 sm:p-6"
          role="main"
          tabIndex={-1}
        >
          <div key={location.pathname} className="animate-fade-in-up">
            <Outlet />
          </div>
        </main>

        {/* Page footer — portfolio-grade */}
        <footer
          className="shrink-0 border-t border-border-subtle bg-surface/60 backdrop-blur-sm
            px-3 py-4 lg:px-4 lg:py-3
            flex flex-col lg:flex-row lg:items-center gap-3 lg:gap-4
            text-xs text-text-secondary"
          aria-label="Rodape do site"
        >
          {/* Author + version */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>
              Built by{' '}
              <strong className="font-semibold text-primary-700 dark:text-primary-400">
                Pedro Marques
              </strong>
            </span>
            <span className="text-text-muted">v0.1.0</span>
          </div>

          <div className="hidden lg:block flex-1" aria-hidden="true" />

          {/* Icon links */}
          <nav
            className="flex items-center gap-1"
            aria-label="Links externos do autor"
          >
            <a
              href="https://github.com/Pedrom2002/energy-forecast-pt"
              target="_blank"
              rel="noopener noreferrer"
              title="GitHub"
              aria-label="Abrir repositorio no GitHub (nova aba)"
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
              aria-label="Abrir perfil do LinkedIn (nova aba)"
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
              title="API Docs"
              aria-label="Abrir documentacao da API (nova aba)"
              className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] rounded-lg
                text-text-secondary hover:text-primary-600 transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            >
              <BookOpen className="w-4 h-4" aria-hidden="true" />
            </a>
          </nav>

          {/* Dark mode toggle + API status */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={toggle}
              className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] rounded-lg
                text-text-secondary hover:text-primary-600 transition-colors cursor-pointer
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
              aria-label={isDark ? 'Mudar para tema claro' : 'Mudar para tema escuro'}
              title={isDark ? 'Tema claro' : 'Tema escuro'}
            >
              {isDark ? <Sun className="w-4 h-4" aria-hidden="true" /> : <Moon className="w-4 h-4" aria-hidden="true" />}
            </button>
            <div
              className="flex items-center gap-2"
              aria-live="polite"
              title={apiOnline ? 'API online' : 'API offline'}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  apiOnline ? 'bg-energy-green animate-pulse' : 'bg-text-muted'
                }`}
                aria-hidden="true"
              />
              <span className="text-[11px] text-text-muted">
                API {apiOnline ? 'online' : 'offline'}
              </span>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}
