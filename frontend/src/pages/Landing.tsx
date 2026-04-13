import { motion } from 'motion/react';
import { Link } from 'react-router-dom';
import {
  Activity,
  Layers,
  Zap,
  TrendingUp,
  Settings,
  Shield,
  Server,
  Code,
  FileCode,
  Palette,
  GitBranch,
  Container,
  TestTube,
  Database,
  Workflow,
  Cpu,
  Globe,
  ChevronDown,
  ArrowRight,
  Github,
  Linkedin,
} from 'lucide-react';
import { AnimatedNumber } from '../components/motion/AnimatedNumber';
import { BentoCard } from '../components/motion/BentoCard';
import { FadeInView } from '../components/motion/FadeInView';
import { GlassCard } from '../components/motion/GlassCard';
import { StaggerGroup, StaggerItem } from '../components/motion/StaggerGroup';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { PORTUGAL_PATH } from '../assets/portugalPath';

interface RegionDot {
  id: string;
  label: string;
  cx: number;
  cy: number;
}

// Coordinates in the 12969 × 26674 viewBox of the continental Portugal path.
// Approximate centroids of the 5 NUTS-II regions (lat/lon mapped linearly onto
// the viewBox: lat 37-42°N, lon -9.5/-6.5°W).
const REGIONS: RegionDot[] = [
  { id: 'norte', label: 'Norte', cx: 6200, cy: 2800 },
  { id: 'centro', label: 'Centro', cx: 6400, cy: 10500 },
  { id: 'lisboa', label: 'Lisboa', cx: 1100, cy: 17200 },
  { id: 'alentejo', label: 'Alentejo', cx: 7400, cy: 19800 },
  { id: 'algarve', label: 'Algarve', cx: 6000, cy: 25600 },
];

interface TechPill {
  label: string;
  Icon: typeof Zap;
}

const TECH_PILLS: TechPill[] = [
  { label: 'XGBoost', Icon: Zap },
  { label: 'CatBoost', Icon: Layers },
  { label: 'LightGBM', Icon: TrendingUp },
  { label: 'Optuna', Icon: Settings },
  { label: 'Conformal', Icon: Shield },
  { label: 'FastAPI', Icon: Server },
  { label: 'React 19', Icon: Code },
  { label: 'TypeScript', Icon: FileCode },
  { label: 'Tailwind', Icon: Palette },
  { label: 'DVC', Icon: GitBranch },
  { label: 'Docker', Icon: Container },
  { label: 'Playwright', Icon: TestTube },
];

interface ArchStep {
  title: string;
  description: string;
  Icon: typeof Database;
}

const ARCH_STEPS: ArchStep[] = [
  { title: 'Dados', description: 'e-Redes CP4 + Open-Meteo', Icon: Database },
  { title: 'Pipeline', description: '78 features + Optuna + 5-fold CV', Icon: Workflow },
  { title: 'Modelo', description: 'XGBoost + Split Conformal', Icon: Cpu },
  { title: 'API + UI', description: 'FastAPI + React 19', Icon: Globe },
];

function PortugalMap() {
  return (
    <svg
      viewBox="0 0 12969 26674"
      className="h-full w-full max-h-[240px]"
      aria-label="Mapa de Portugal continental com 5 regiões"
      role="img"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <linearGradient id="pt-fill" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="var(--color-primary-400, #fbbf24)" />
          <stop offset="100%" stopColor="var(--color-primary-600, #d97706)" />
        </linearGradient>
      </defs>
      {/* Continental Portugal — data from AfonsoFG/PortugalSVG (CC BY-SA 4.0) */}
      <path
        d={PORTUGAL_PATH}
        fill="url(#pt-fill)"
        stroke="#b45309"
        strokeOpacity={0.45}
        strokeWidth={40}
        strokeLinejoin="round"
      />
      {/* Region dots with pulsing halo */}
      {REGIONS.map((r, i) => (
        <g key={r.id}>
          <motion.circle
            cx={r.cx}
            cy={r.cy}
            r={650}
            className="fill-white/70"
            animate={{ scale: [1, 1.9, 1], opacity: [0.55, 0, 0.55] }}
            transition={{ duration: 2, repeat: Infinity, delay: i * 0.3 }}
            style={{ transformOrigin: `${r.cx}px ${r.cy}px` }}
          />
          <circle
            cx={r.cx}
            cy={r.cy}
            r={240}
            className="fill-white stroke-primary-900"
            strokeWidth={80}
          />
        </g>
      ))}
    </svg>
  );
}

export default function Landing() {
  useDocumentTitle('Início');

  return (
    <div className="min-h-screen bg-background text-text-primary">
      {/* ── Section 1: Hero ─────────────────────────────────────────── */}
      <section
        aria-label="Introdução"
        className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-primary-50/40 via-background to-accent-50/20 px-4 md:px-6"
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-1/2 top-1/2 h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary-300/20 blur-3xl dark:bg-primary-700/20"
        />

        <div className="container relative z-10 mx-auto max-w-7xl text-center">
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0, ease: [0.22, 1, 0.36, 1] }}
            className="mb-6 text-xs font-medium uppercase tracking-[0.2em] text-text-secondary"
          >
            Machine Learning · Portfolio
          </motion.p>

          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
            className="mb-6 text-4xl font-bold tracking-tight md:text-6xl lg:text-7xl"
          >
            <span className="block">Previsão energética</span>
            <span className="block">
              para{' '}
              <span className="bg-gradient-to-r from-primary-500 to-accent bg-clip-text text-transparent">
                Portugal
              </span>
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="mx-auto mb-10 max-w-2xl text-lg text-text-secondary md:text-xl"
          >
            ML de produção com intervalos de confiança. MAPE 1.44%, RMSE 22.9 MW,
            2.6× melhor que o baseline.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="flex flex-col items-center justify-center gap-4 sm:flex-row"
          >
            <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              <Link
                to="/predict"
                className="inline-flex items-center gap-2 rounded-xl bg-primary-500 px-6 py-3 font-semibold text-white shadow-lg shadow-primary-500/30 transition-colors hover:bg-primary-600"
              >
                Experimenta agora
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </motion.div>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-transparent px-6 py-3 font-semibold text-text-primary transition-colors hover:bg-surface"
            >
              Ver documentação
            </a>
          </motion.div>
        </div>

        <motion.div
          aria-hidden="true"
          className="absolute bottom-8 left-1/2 -translate-x-1/2 text-text-secondary"
          animate={{ y: [0, 8, 0] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        >
          <ChevronDown className="h-6 w-6" />
        </motion.div>
      </section>

      {/* ── Section 2: Live metrics bento ───────────────────────────── */}
      <section
        aria-label="Métricas do modelo"
        className="container mx-auto max-w-7xl px-4 py-16 md:px-6 md:py-24"
      >
        <FadeInView className="mb-12 text-center">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-secondary">
            Performance
          </p>
          <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
            Métricas reais em produção
          </h2>
        </FadeInView>

        <FadeInView>
          <div className="grid auto-rows-[minmax(140px,auto)] grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 lg:gap-6">
            {/* 1. Big MAPE */}
            <BentoCard size="xl" gradient className="flex flex-col justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                  Precisão
                </p>
                <h3 className="mt-2 text-lg font-semibold">MAPE</h3>
              </div>
              <div className="flex items-baseline gap-2">
                <AnimatedNumber
                  value={1.44}
                  format={(n) => n.toFixed(2)}
                  className="text-6xl font-bold text-primary-500 md:text-8xl"
                />
                <span className="text-3xl font-bold text-primary-500 md:text-5xl">%</span>
              </div>
              <div>
                <p className="mb-3 text-sm text-text-secondary">
                  Mean Absolute Percentage Error
                </p>
                <span className="inline-flex items-center rounded-full bg-primary-100 px-3 py-1 text-xs font-semibold text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">
                  2.6× melhor que persistência
                </span>
              </div>
            </BentoCard>

            {/* 2. RMSE */}
            <BentoCard size="sm" className="flex flex-col justify-between">
              <div className="flex items-start justify-between">
                <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                  RMSE
                </p>
                <Activity className="h-4 w-4 text-primary-500" aria-hidden="true" />
              </div>
              <div className="flex items-baseline gap-1">
                <AnimatedNumber
                  value={22.9}
                  format={(n) => n.toFixed(1)}
                  className="text-3xl font-bold md:text-4xl"
                />
                <span className="text-lg font-semibold text-text-secondary">MW</span>
              </div>
            </BentoCard>

            {/* 3. Models */}
            <BentoCard size="sm" className="flex flex-col justify-between">
              <div className="flex items-start justify-between">
                <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                  Modelos
                </p>
                <Layers className="h-4 w-4 text-primary-500" aria-hidden="true" />
              </div>
              <div className="flex items-baseline gap-2">
                <AnimatedNumber
                  value={2}
                  format={(n) => Math.round(n).toString()}
                  className="text-3xl font-bold md:text-4xl"
                />
                <span className="text-sm text-text-secondary">ativos</span>
              </div>
            </BentoCard>

            {/* 4. R² */}
            <BentoCard size="lg" className="flex flex-col justify-between">
              <div className="flex items-start justify-between">
                <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                  Coeficiente R²
                </p>
                <TrendingUp className="h-4 w-4 text-primary-500" aria-hidden="true" />
              </div>
              <div className="flex items-baseline gap-2">
                <AnimatedNumber
                  value={0.998}
                  format={(n) => n.toFixed(3)}
                  className="text-4xl font-bold md:text-5xl"
                />
              </div>
              <div
                className="h-2 w-full overflow-hidden rounded-full bg-surface-subtle"
                role="progressbar"
                aria-valuenow={99.8}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <motion.div
                  className="h-full rounded-full bg-gradient-to-r from-primary-500 to-accent"
                  initial={{ width: 0 }}
                  whileInView={{ width: '99.8%' }}
                  viewport={{ once: true, margin: '-40px' }}
                  transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
                />
              </div>
            </BentoCard>

            {/* 5. Regions */}
            <BentoCard size="md" className="flex flex-col items-center justify-between">
              <p className="w-full text-xs font-medium uppercase tracking-wide text-text-secondary">
                Cobertura
              </p>
              <div className="flex flex-1 items-center justify-center py-4">
                <PortugalMap />
              </div>
              <div className="w-full text-center">
                <p className="text-2xl font-bold">
                  <AnimatedNumber value={5} format={(n) => Math.round(n).toString()} />{' '}
                  <span className="text-sm font-medium text-text-secondary">regiões</span>
                </p>
              </div>
            </BentoCard>

            {/* 6. Samples */}
            <BentoCard size="sm" className="flex flex-col justify-between">
              <div className="flex items-start justify-between">
                <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                  Amostras
                </p>
                <Database className="h-4 w-4 text-primary-500" aria-hidden="true" />
              </div>
              <div>
                <AnimatedNumber
                  value={40075}
                  format={(n) => Math.round(n).toLocaleString('pt-PT')}
                  className="text-3xl font-bold md:text-4xl"
                />
                <p className="mt-1 text-xs text-text-secondary">e-Redes + Open-Meteo</p>
              </div>
            </BentoCard>
          </div>
        </FadeInView>
      </section>

      {/* ── Section 3: Tech stack ───────────────────────────────────── */}
      <section
        aria-label="Stack tecnológica"
        className="container mx-auto max-w-7xl px-4 py-16 md:px-6 md:py-24"
      >
        <FadeInView className="mb-12 text-center">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-secondary">
            Stack
          </p>
          <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
            Tecnologias usadas em produção
          </h2>
        </FadeInView>

        <StaggerGroup className="flex flex-wrap items-center justify-center gap-3">
          {TECH_PILLS.map(({ label, Icon }) => (
            <StaggerItem key={label}>
              <GlassCard className="inline-flex items-center gap-2 px-4 py-2" hover>
                <Icon className="h-4 w-4 text-primary-500" aria-hidden="true" />
                <span className="text-sm font-medium">{label}</span>
              </GlassCard>
            </StaggerItem>
          ))}
        </StaggerGroup>
      </section>

      {/* ── Section 4: Architecture flow ────────────────────────────── */}
      <section
        aria-label="Arquitectura"
        className="container mx-auto max-w-7xl px-4 py-16 md:px-6 md:py-24"
      >
        <FadeInView className="mb-12 text-center">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-secondary">
            Arquitectura
          </p>
          <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
            Do dado bruto à previsão
          </h2>
        </FadeInView>

        <div className="flex flex-col items-stretch gap-4 lg:flex-row lg:items-center">
          {ARCH_STEPS.map(({ title, description, Icon }, idx) => (
            <div key={title} className="flex flex-col items-center gap-4 lg:flex-1 lg:flex-row">
              <FadeInView delay={idx * 0.1} className="w-full">
                <BentoCard size="sm" className="h-full min-h-[160px] w-full">
                  <div className="flex h-full flex-col items-start gap-3">
                    <div className="rounded-lg bg-primary-100 p-2 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300">
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </div>
                    <div>
                      <h3 className="mb-1 text-lg font-semibold">{title}</h3>
                      <p className="text-sm text-text-secondary">{description}</p>
                    </div>
                  </div>
                </BentoCard>
              </FadeInView>
              {idx < ARCH_STEPS.length - 1 && (
                <div
                  aria-hidden="true"
                  className="flex items-center justify-center text-text-secondary"
                >
                  <ArrowRight className="hidden h-5 w-5 lg:block" />
                  <ChevronDown className="h-5 w-5 lg:hidden" />
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ── Section 5: Try it CTA ───────────────────────────────────── */}
      <section
        aria-label="Experimentar"
        className="container mx-auto max-w-7xl px-4 py-16 md:px-6 md:py-24"
      >
        <FadeInView>
          <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-primary-500 via-accent to-primary-600 p-8 text-white shadow-xl md:p-16">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-white/10 blur-3xl"
            />
            <div
              aria-hidden="true"
              className="pointer-events-none absolute -bottom-20 -left-20 h-64 w-64 rounded-full bg-white/10 blur-3xl"
            />
            <div className="relative text-center">
              <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-5xl">
                Pronto para tentar?
              </h2>
              <p className="mx-auto mb-10 max-w-xl text-lg text-white/90">
                Gera uma previsão em segundos, sem registo.
              </p>
              <div className="flex flex-col flex-wrap items-center justify-center gap-3 sm:flex-row">
                <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                  <Link
                    to="/predict"
                    className="inline-flex items-center gap-2 rounded-xl bg-white px-6 py-3 font-semibold text-primary-600 shadow-lg transition-colors hover:bg-white/90"
                  >
                    Prever 1 hora
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </motion.div>
                <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                  <Link
                    to="/forecast"
                    className="inline-flex items-center gap-2 rounded-xl border border-white/40 bg-white/10 px-6 py-3 font-semibold text-white backdrop-blur-sm transition-colors hover:bg-white/20"
                  >
                    Forecast 24h
                  </Link>
                </motion.div>
                <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                  <Link
                    to="/batch"
                    className="inline-flex items-center gap-2 rounded-xl border border-white/40 bg-white/10 px-6 py-3 font-semibold text-white backdrop-blur-sm transition-colors hover:bg-white/20"
                  >
                    Batch CSV
                  </Link>
                </motion.div>
              </div>
            </div>
          </div>
        </FadeInView>
      </section>

      {/* ── Section 6: Author footer ────────────────────────────────── */}
      <section
        aria-label="Autor"
        className="container mx-auto max-w-7xl px-4 pb-16 pt-8 md:px-6 md:pb-24"
      >
        <FadeInView>
          <GlassCard className="mx-auto flex max-w-2xl flex-col items-center justify-center gap-4 p-6 sm:flex-row sm:gap-6">
            <div
              aria-hidden="true"
              className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-accent text-lg font-bold text-white shadow-md"
            >
              PM
            </div>
            <div className="text-center sm:text-left">
              <p className="text-sm text-text-secondary">Built by</p>
              <p className="text-lg font-semibold">Pedro Marques</p>
            </div>
            <div className="flex items-center gap-3 sm:ml-auto">
              <a
                href="https://github.com/pedrom2002"
                target="_blank"
                rel="noreferrer"
                aria-label="GitHub"
                className="rounded-lg border border-border p-2 text-text-secondary transition-colors hover:border-primary-300 hover:text-primary-500"
              >
                <Github className="h-5 w-5" />
              </a>
              <a
                href="https://linkedin.com/"
                target="_blank"
                rel="noreferrer"
                aria-label="LinkedIn"
                className="rounded-lg border border-border p-2 text-text-secondary transition-colors hover:border-primary-300 hover:text-primary-500"
              >
                <Linkedin className="h-5 w-5" />
              </a>
            </div>
          </GlassCard>
        </FadeInView>
      </section>
    </div>
  );
}
