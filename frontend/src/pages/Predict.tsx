import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { type EnergyData } from '../api/client';
import { usePredictMutation } from '../api/hooks';
import { Card } from '../components/Card';
import { toast } from '../components/Toast';
import { formatMW, formatDateTime } from '../utils/format';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import WeatherForm from '../components/WeatherForm';
import { Zap, ArrowRight, TrendingUp, TrendingDown, Shield, HelpCircle } from 'lucide-react';

function getDefaultTimestamp(): string {
  const now = new Date();
  now.setMinutes(0, 0, 0);
  return now.toISOString().slice(0, 19);
}

export default function Predict() {
  const { t } = useTranslation();
  useDocumentTitle(t('predict.title'));
  const [data, setData] = useState<EnergyData>({
    timestamp: getDefaultTimestamp(),
    region: 'Lisboa',
    temperature: 18.5,
    humidity: 65.0,
    wind_speed: 12.3,
    precipitation: 0.0,
    cloud_cover: 40.0,
    pressure: 1015.0,
  });
  const predictMutation = usePredictMutation({
    onSuccess: (res) => {
      toast.success(
        t('predict.toastSuccess', {
          value: formatMW(res.predicted_consumption_mw),
          region: res.region,
        }),
      );
    },
  });
  const result = predictMutation.data ?? null;
  const loading = predictMutation.isPending;
  const error = predictMutation.error
    ? predictMutation.error.message || t('common.unknownError')
    : null;

  const handlePredict = () => {
    predictMutation.mutate(data);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-semibold text-text-primary tracking-tight">
          {t('predict.title')}
        </h1>
        <p className="text-sm text-text-secondary mt-1.5">{t('predict.subtitle')}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        {/* Form column */}
        <Card
          title={t('predict.params')}
          subtitle={t('predict.paramsSubtitle')}
          className="lg:col-span-2"
        >
          <WeatherForm data={data} onChange={setData} idPrefix="pred" />
          <button
            type="button"
            onClick={handlePredict}
            disabled={loading}
            className="mt-6 w-full flex items-center justify-center gap-2
              bg-primary-500 hover:bg-primary-400 disabled:bg-primary-500/40 disabled:cursor-not-allowed
              text-[#05080f] font-semibold min-h-[48px] px-4 rounded-lg
              transition-all duration-200 cursor-pointer
              shadow-[0_0_20px_rgba(34,211,238,0.35)] hover:shadow-[0_0_28px_rgba(34,211,238,0.5)]
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[#05080f]
              active:scale-[0.98]"
            aria-busy={loading}
          >
            {loading ? (
              <div
                className="animate-spin w-5 h-5 border-2 border-[#05080f]/30 border-t-[#05080f] rounded-full"
                role="status"
              >
                <span className="sr-only">{t('common.processing')}</span>
              </div>
            ) : (
              <>
                <Zap className="w-4 h-4" strokeWidth={2.5} aria-hidden="true" />
                {t('predict.predictButton')}
                <ArrowRight className="w-4 h-4" aria-hidden="true" />
              </>
            )}
          </button>
        </Card>

        {/* Result column */}
        <div className="lg:col-span-3 space-y-4">
          {error && (
            <div
              className="rounded-xl border border-rose-500/25 bg-rose-500/[0.05] p-4 animate-fade-in-up"
              role="alert"
            >
              <p className="text-sm text-rose-200 font-medium">
                {t('predict.errorPrefix')}: {error}
              </p>
              <p className="text-xs text-rose-300/70 mt-1">{t('predict.errorHint')}</p>
            </div>
          )}

          {result && (
            <div className="space-y-4 stagger-children">
              {/* Main prediction hero */}
              <div
                className="relative overflow-hidden rounded-2xl border border-primary-400/25 bg-surface p-6 sm:p-8
                  shadow-[var(--shadow-glow)]"
                aria-live="polite"
              >
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0
                    bg-[radial-gradient(ellipse_100%_80%_at_0%_0%,rgba(34,211,238,0.15),transparent_60%),radial-gradient(ellipse_60%_80%_at_100%_100%,rgba(245,158,11,0.08),transparent_60%)]"
                />
                <div className="relative">
                  <div className="flex items-center gap-2 text-[10px] font-mono font-semibold uppercase tracking-[0.14em] text-primary-300">
                    <Zap className="w-3.5 h-3.5" aria-hidden="true" />
                    {t('predict.predictedConsumption')}
                  </div>
                  <p className="mt-3 font-display text-5xl sm:text-6xl font-semibold text-text-primary tracking-tight leading-none tabular-nums">
                    {formatMW(result.predicted_consumption_mw)}
                  </p>
                  <p className="mt-4 text-sm font-mono text-text-secondary uppercase tracking-wider">
                    {result.region} <span className="text-text-muted">·</span>{' '}
                    {formatDateTime(result.timestamp)}
                  </p>
                </div>
              </div>

              {/* CI card */}
              <Card
                title={t('predict.ci')}
                subtitle={`${(result.confidence_level * 100).toFixed(0)}% · ${t('predict.ciMethod')}: ${result.ci_method}`}
                action={
                  <span title={t('predict.ciTooltip')} className="inline-flex items-center">
                    <HelpCircle className="w-4 h-4 text-text-muted" aria-label={t('predict.ciTooltip')} />
                  </span>
                }
              >
                <div className="grid grid-cols-3 gap-2 sm:gap-3">
                  <CIBound
                    icon={<TrendingDown className="w-4 h-4" aria-hidden="true" />}
                    label={t('predict.lowerBound')}
                    value={formatMW(result.confidence_interval_lower)}
                    tone="muted"
                    clipped={result.ci_lower_clipped}
                  />
                  <CIBound
                    icon={<Zap className="w-4 h-4" aria-hidden="true" />}
                    label={t('predict.prediction')}
                    value={formatMW(result.predicted_consumption_mw)}
                    tone="primary"
                  />
                  <CIBound
                    icon={<TrendingUp className="w-4 h-4" aria-hidden="true" />}
                    label={t('predict.upperBound')}
                    value={formatMW(result.confidence_interval_upper)}
                    tone="muted"
                  />
                </div>

                <div
                  className="mt-5"
                  role="img"
                  aria-label={t('predict.ciBarAria', {
                    lower: result.confidence_interval_lower.toFixed(0),
                    upper: result.confidence_interval_upper.toFixed(0),
                  })}
                >
                  <div className="relative h-2.5 bg-surface-dim rounded-full overflow-hidden border border-border-subtle">
                    {(() => {
                      const range = result.confidence_interval_upper - result.confidence_interval_lower;
                      const predPos = range > 0
                        ? ((result.predicted_consumption_mw - result.confidence_interval_lower) / range) * 100
                        : 50;
                      return (
                        <>
                          <div
                            className="absolute inset-0 rounded-full
                              bg-gradient-to-r from-primary-500/30 via-primary-400/50 to-primary-500/30"
                          />
                          <div
                            className="absolute top-0 bottom-0 w-[3px] bg-primary-300 rounded-full
                              shadow-[0_0_8px_rgba(34,211,238,0.9)] transition-all duration-300"
                            style={{ left: `${Math.max(0, Math.min(100, predPos))}%` }}
                          />
                        </>
                      );
                    })()}
                  </div>
                  <div className="flex justify-between text-[11px] font-mono text-text-muted mt-1.5 tabular-nums">
                    <span>{formatMW(result.confidence_interval_lower, 0)}</span>
                    <span>{formatMW(result.confidence_interval_upper, 0)}</span>
                  </div>
                </div>
              </Card>

              {/* Model info strip */}
              <div className="grid grid-cols-2 gap-3 sm:gap-4">
                <MetaTile
                  icon={<Shield className="w-3.5 h-3.5" aria-hidden="true" />}
                  label={t('predict.methodCI')}
                  value={result.ci_method === 'conformal' ? t('predict.conformal') : t('predict.gaussian')}
                />
                <MetaTile
                  icon={<Zap className="w-3.5 h-3.5" aria-hidden="true" />}
                  label={t('predict.model')}
                  value={result.model_name}
                />
              </div>
            </div>
          )}

          {!result && !error && (
            <div className="glass-card p-10 sm:p-14 text-center">
              <div
                className="w-14 h-14 rounded-xl bg-primary-500/10 ring-1 ring-primary-400/20
                  flex items-center justify-center mx-auto mb-4"
              >
                <Zap className="w-7 h-7 text-primary-400" aria-hidden="true" />
              </div>
              <p className="text-sm font-medium text-text-secondary">{t('predict.readyTitle')}</p>
              <p className="text-xs text-text-muted mt-1.5 max-w-xs mx-auto leading-relaxed">
                {t('predict.readyHint')}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CIBound({
  icon,
  label,
  value,
  tone,
  clipped,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: 'muted' | 'primary';
  clipped?: boolean;
}) {
  const isPrimary = tone === 'primary';
  return (
    <div
      className={`flex-1 text-center p-3 sm:p-4 rounded-lg
        ${isPrimary
          ? 'bg-primary-500/10 border border-primary-400/30 shadow-[0_0_16px_rgba(34,211,238,0.15)]'
          : 'bg-surface-dim border border-border-subtle hover:border-border-strong transition-colors'
        }`}
    >
      <div className={isPrimary ? 'text-primary-300' : 'text-text-muted'}>
        {icon}
      </div>
      <p className="text-[10px] font-mono uppercase tracking-wider text-text-muted mt-1.5">{label}</p>
      <p
        className={`mt-1 text-base sm:text-lg font-display font-semibold tabular-nums tracking-tight
          ${isPrimary ? 'text-primary-300' : 'text-text-primary'}`}
      >
        {value}
      </p>
      {clipped && (
        <span
          className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider
            text-energy-yellow bg-yellow-500/10 ring-1 ring-yellow-400/20 px-1.5 py-0.5 rounded mt-1.5"
        >
          <Shield className="w-2.5 h-2.5" aria-hidden="true" /> clipped
        </span>
      )}
    </div>
  );
}

function MetaTile({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="glass-card p-4">
      <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.12em] text-text-muted mb-1.5">
        {icon}
        {label}
      </div>
      <p className="text-sm font-mono font-semibold text-text-primary truncate">{value}</p>
    </div>
  );
}
