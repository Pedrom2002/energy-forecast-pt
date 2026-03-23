"""
Generate analysis notebooks (EDA, evaluation, error analysis, validation).

These notebooks are analysis-only: they load pre-trained models from
``data/models/`` and perform evaluation, visualization, and diagnostics.
Model training is handled by ``scripts/retrain.py`` (pipeline v5).

Notebooks generated:
  01 - Exploratory Data Analysis (EDA) — pure visualization
  02 - Model Evaluation — loads 3 variants, compares metrics
  03 - Advanced Feature Analysis — loads advanced model, analyzes features
  04 - Error Analysis — error by region/hour/season, residual diagnostics
  05 - Robust Validation — walk-forward CV, seasonal backtest (ephemeral training)

Usage:
  python scripts/generate_notebooks.py
  python scripts/retrain.py          # train models first!
  python run_notebooks.py            # then run analysis notebooks
"""

from pathlib import Path

import nbformat as nbf

NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent / "notebooks"


def md(source: str) -> nbf.v4.new_markdown_cell:
    return nbf.v4.new_markdown_cell(source.strip())


def code(source: str) -> nbf.v4.new_code_cell:
    return nbf.v4.new_code_cell(source.strip())


def save(nb, name):
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    path = NOTEBOOKS_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        nbf.write(nb, f)
    print(f"  -> {path.name}")


# ============================================================
# NOTEBOOK 01 - Exploratory Data Analysis (unchanged)
# ============================================================
def create_nb01():
    nb = nbf.v4.new_notebook()
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.cells = [
        md(
            "# 01 - Analise Exploratoria de Dados (EDA)\n\nAnalise completa dos dados de consumo energetico de Portugal."
        ),
        code("""import sys
sys.path.append('..')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
import warnings

warnings.filterwarnings('ignore')
plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['figure.figsize'] = (14, 6)
plt.rcParams['font.size'] = 12

print('Bibliotecas carregadas')"""),
        md("## 1. Carregamento dos Dados"),
        code("""df = pd.read_parquet('../data/processed/processed_data.parquet')

print(f"Dimensoes: {df.shape}")
print(f"Periodo: {df['timestamp'].min()} a {df['timestamp'].max()}")
print(f"Regioes: {df['region'].nunique()} - {sorted(df['region'].unique())}")
print(f"\\nColunas ({len(df.columns)}):")
for col in df.columns:
    print(f"  {col:25s} {str(df[col].dtype):10s} nulls={df[col].isnull().sum()}")"""),
        md("## 2. Estatisticas Descritivas"),
        code("""target = 'consumption_mw'

print("=" * 70)
print("ESTATISTICAS DO CONSUMO ENERGETICO (MW)")
print("=" * 70)
desc = df[target].describe()
for k, v in desc.items():
    print(f"  {k:10s}: {v:>12.2f}")

print(f"\\n  Skewness : {df[target].skew():>12.4f}")
print(f"  Kurtosis : {df[target].kurtosis():>12.4f}")

fig, axes = plt.subplots(1, 3, figsize=(18, 5))

axes[0].hist(df[target], bins=50, edgecolor='black', alpha=0.7, color='steelblue')
axes[0].axvline(df[target].mean(), color='red', linestyle='--', label=f'Media={df[target].mean():.0f}')
axes[0].axvline(df[target].median(), color='orange', linestyle='--', label=f'Mediana={df[target].median():.0f}')
axes[0].set_xlabel('Consumo (MW)')
axes[0].set_ylabel('Frequencia')
axes[0].set_title('Distribuicao do Consumo')
axes[0].legend()

stats.probplot(df[target], dist="norm", plot=axes[1])
axes[1].set_title('Q-Q Plot')

df.boxplot(column=target, by='region', ax=axes[2])
axes[2].set_title('Consumo por Regiao')
axes[2].set_xlabel('Regiao')
axes[2].set_ylabel('Consumo (MW)')
plt.suptitle('')

plt.tight_layout()
plt.show()"""),
        md("## 3. Padroes Temporais"),
        code("""df['hour'] = df['timestamp'].dt.hour
df['day_of_week'] = df['timestamp'].dt.dayofweek
df['month'] = df['timestamp'].dt.month
df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)

fig, axes = plt.subplots(2, 2, figsize=(16, 12))

hourly = df.groupby('hour')[target].agg(['mean', 'std'])
axes[0,0].plot(hourly.index, hourly['mean'], 'b-o', linewidth=2)
axes[0,0].fill_between(hourly.index, hourly['mean'] - hourly['std'], hourly['mean'] + hourly['std'], alpha=0.2)
axes[0,0].set_xlabel('Hora')
axes[0,0].set_ylabel('Consumo Medio (MW)')
axes[0,0].set_title('Perfil Horario')
axes[0,0].set_xticks(range(0, 24))

days = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom']
daily = df.groupby('day_of_week')[target].mean()
colors = ['steelblue']*5 + ['coral']*2
axes[0,1].bar(range(7), daily.values, color=colors, edgecolor='black')
axes[0,1].set_xticks(range(7))
axes[0,1].set_xticklabels(days)
axes[0,1].set_ylabel('Consumo Medio (MW)')
axes[0,1].set_title('Perfil Semanal')

monthly = df.groupby('month')[target].mean()
axes[1,0].bar(range(1,13), monthly.values, color='steelblue', edgecolor='black')
axes[1,0].set_xticks(range(1,13))
axes[1,0].set_xticklabels(['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'])
axes[1,0].set_ylabel('Consumo Medio (MW)')
axes[1,0].set_title('Perfil Mensal')

pivot = df.groupby(['day_of_week', 'hour'])[target].mean().unstack()
sns.heatmap(pivot, cmap='YlOrRd', ax=axes[1,1], xticklabels=2)
axes[1,1].set_yticklabels(days, rotation=0)
axes[1,1].set_xlabel('Hora')
axes[1,1].set_title('Mapa de Calor: Hora x Dia da Semana')

plt.tight_layout()
plt.show()

print(f"Hora de pico: {hourly['mean'].idxmax()}h ({hourly['mean'].max():.0f} MW)")
print(f"Hora de vale: {hourly['mean'].idxmin()}h ({hourly['mean'].min():.0f} MW)")"""),
        md("## 4. Analise Regional"),
        code("""fig, axes = plt.subplots(1, 2, figsize=(16, 6))

regional = df.groupby('region')[target].agg(['mean', 'std', 'min', 'max']).sort_values('mean', ascending=True)
regional['mean'].plot(kind='barh', ax=axes[0], color='steelblue', edgecolor='black')
axes[0].set_xlabel('Consumo Medio (MW)')
axes[0].set_title('Consumo Medio por Regiao')

for region in sorted(df['region'].unique()):
    hourly_r = df[df['region'] == region].groupby('hour')[target].mean()
    axes[1].plot(hourly_r.index, hourly_r.values, '-o', label=region, linewidth=2, markersize=4)
axes[1].set_xlabel('Hora')
axes[1].set_ylabel('Consumo (MW)')
axes[1].set_title('Perfil Horario por Regiao')
axes[1].legend()
axes[1].set_xticks(range(0, 24))

plt.tight_layout()
plt.show()

print("\\nEstatisticas por Regiao:")
print(regional.to_string())"""),
        md("## 5. Correlacoes Meteorologicas"),
        code(
            """weather_cols = [c for c in ['temperature', 'humidity', 'wind_speed', 'precipitation', 'cloud_cover', 'pressure'] if c in df.columns]

fig, axes = plt.subplots(2, 3, figsize=(18, 10))
for i, col in enumerate(weather_cols):
    ax = axes[i // 3, i % 3]
    sample = df.sample(min(5000, len(df)), random_state=42)
    ax.scatter(sample[col], sample[target], alpha=0.3, s=10)
    ax.set_xlabel(col)
    ax.set_ylabel('Consumo (MW)')
    corr = df[col].corr(df[target])
    ax.set_title(f'{col} (r={corr:.4f})')

plt.suptitle('Correlacoes Meteorologicas', fontsize=16, y=1.02)
plt.tight_layout()
plt.show()

print("\\nCorrelacoes com consumo:")
for col in weather_cols:
    r = df[col].corr(df[target])
    print(f"  {col:20s}: {r:+.4f}")"""
        ),
        md("## 6. Analise de Autocorrelacao"),
        code("""df_lisboa = df[df['region'] == 'Lisboa'].sort_values('timestamp').set_index('timestamp')

fig, axes = plt.subplots(2, 1, figsize=(14, 8))
plot_acf(df_lisboa[target].dropna().values[:2000], lags=72, ax=axes[0])
axes[0].set_title('ACF - Autocorrelacao (Lisboa)')
axes[0].set_xlabel('Lag (horas)')

plot_pacf(df_lisboa[target].dropna().values[:2000], lags=72, ax=axes[1], method='ywm')
axes[1].set_title('PACF - Autocorrelacao Parcial (Lisboa)')
axes[1].set_xlabel('Lag (horas)')

plt.tight_layout()
plt.show()

print("Observacoes:")
print("  - Forte autocorrelacao com periodicidade de 24h (padrao diario)")
print("  - Decaimento lento da ACF indica tendencia ou sazonalidade longa")"""),
        md("## 7. Decomposicao Sazonal"),
        code("""df_decomp = df_lisboa[target].resample('h').mean().dropna()[:90*24]

decomposition = seasonal_decompose(df_decomp, model='additive', period=24)

fig, axes = plt.subplots(4, 1, figsize=(14, 12))
decomposition.observed.plot(ax=axes[0], title='Observado')
decomposition.trend.plot(ax=axes[1], title='Tendencia')
decomposition.seasonal.plot(ax=axes[2], title='Sazonalidade (24h)')
decomposition.resid.plot(ax=axes[3], title='Residuo')

for ax in axes:
    ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()

var_total = df_decomp.var()
var_resid = decomposition.resid.var()
var_explained = (1 - var_resid / var_total) * 100
print(f"\\nVariancia explicada pela decomposicao: {var_explained:.2f}%")"""),
        md("## 8. Deteccao de Outliers"),
        code("""Q1 = df[target].quantile(0.25)
Q3 = df[target].quantile(0.75)
IQR = Q3 - Q1
lower = Q1 - 1.5 * IQR
upper = Q3 + 1.5 * IQR

outliers_iqr = df[(df[target] < lower) | (df[target] > upper)]

from scipy.stats import zscore
z = np.abs(zscore(df[target].dropna()))
outliers_z = df.loc[df.index.isin(df[target].dropna().index[z > 3])]

print("=" * 50)
print("DETECCAO DE OUTLIERS")
print("=" * 50)
print(f"IQR: {len(outliers_iqr)} outliers ({len(outliers_iqr)/len(df)*100:.3f}%)")
print(f"  Limites: [{lower:.0f}, {upper:.0f}] MW")
print(f"Z-score (>3): {len(outliers_z)} outliers ({len(outliers_z)/len(df)*100:.3f}%)")

fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(df['timestamp'], df[target], alpha=0.3, linewidth=0.5)
ax.scatter(outliers_iqr['timestamp'], outliers_iqr[target], color='red', s=20, label=f'Outliers IQR ({len(outliers_iqr)})')
ax.axhline(upper, color='red', linestyle='--', alpha=0.5)
ax.axhline(lower, color='red', linestyle='--', alpha=0.5)
ax.set_xlabel('Data')
ax.set_ylabel('Consumo (MW)')
ax.set_title('Deteccao de Outliers')
ax.legend()
plt.tight_layout()
plt.show()"""),
        md("## 9. Resumo"),
        code("""print("=" * 70)
print("RESUMO DA ANALISE EXPLORATORIA")
print("=" * 70)
print(f\"\"\"
DADOS:
  Periodo: {df['timestamp'].min().date()} a {df['timestamp'].max().date()}
  Registos: {len(df):,}
  Regioes: {', '.join(sorted(df['region'].unique()))}

CONSUMO:
  Media: {df[target].mean():.2f} MW
  Mediana: {df[target].median():.2f} MW
  Desvio-padrao: {df[target].std():.2f} MW
  Amplitude: [{df[target].min():.0f}, {df[target].max():.0f}] MW

PADROES:
  - Forte padrao diario (pico ~14h, vale ~22h)
  - Fim-de-semana com consumo inferior
  - Variacao sazonal (inverno > verao)
  - Lisboa domina o consumo (> 2500 MW medio)

QUALIDADE:
  - Outliers: {len(outliers_iqr)} ({len(outliers_iqr)/len(df)*100:.3f}%)
  - Valores nulos: {df[target].isnull().sum()}
  - Distribuicao: assimetria positiva ({df[target].skew():.3f})
\"\"\")"""),
    ]
    save(nb, "01_exploratory_data_analysis.ipynb")


# ============================================================
# NOTEBOOK 02 - Model Evaluation (load-only, no training)
# ============================================================
def create_nb02():
    nb = nbf.v4.new_notebook()
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.cells = [
        md("""# 02 - Avaliacao de Modelos

Comparacao detalhada dos 3 modelos treinados (with lags, no lags, advanced).

**Nota:** Os modelos devem ser treinados primeiro com `python scripts/retrain.py`."""),
        code("""import sys
sys.path.append('..')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import joblib
import json
import warnings

from src.features.feature_engineering import FeatureEngineer
from src.models.evaluation import ModelEvaluator

warnings.filterwarnings('ignore')
plt.style.use('seaborn-v0_8-darkgrid')"""),
        md("## 1. Carregar Metadados e Modelos"),
        code("""models_dir = Path('../data/models')
evaluator = ModelEvaluator()

# Carregar metadados dos 3 variantes
variants = {}
variant_configs = {
    'with_lags': {
        'meta': 'metadata/training_metadata.json',
        'model': 'checkpoints/best_model.pkl',
        'features': 'features/feature_names.txt',
    },
    'no_lags': {
        'meta': 'metadata/training_metadata_no_lags.json',
        'model': 'checkpoints/best_model_no_lags.pkl',
        'features': 'features/feature_names_no_lags.txt',
    },
    'advanced': {
        'meta': 'metadata/metadata_advanced.json',
        'model': 'checkpoints/best_model_advanced.pkl',
        'features': 'features/advanced_feature_names.txt',
    },
}

for name, paths in variant_configs.items():
    meta_path = models_dir / paths['meta']
    model_path = models_dir / paths['model']
    feat_path = models_dir / paths['features']

    if not model_path.exists():
        print(f"  [{name}] Modelo nao encontrado: {model_path}")
        continue

    with open(meta_path) as f:
        meta = json.load(f)
    model = joblib.load(model_path)
    with open(feat_path) as f:
        feature_names = [l.strip() for l in f.readlines() if l.strip()]

    variants[name] = {'meta': meta, 'model': model, 'features': feature_names}
    print(f"  [{name}] {meta.get('best_model', 'N/A')} | {len(feature_names)} features | "
          f"RMSE={meta['test_metrics']['rmse']:.2f} | MAPE={meta['test_metrics']['mape']:.2f}%")

print(f"\\n{len(variants)} variante(s) carregada(s)")"""),
        md("## 2. Reavaliar no Conjunto de Teste"),
        code("""df = pd.read_parquet('../data/processed/processed_data.parquet')
fe = FeatureEngineer()

results = {}
for name, v in variants.items():
    if name == 'no_lags':
        df_feat = fe.create_features_no_lags(df)
    elif name == 'advanced':
        df_feat = fe.create_all_features(df, use_advanced=True)
    else:
        df_feat = fe.create_all_features(df)

    df_sorted = df_feat.sort_values('timestamp').reset_index(drop=True)
    test_start = int(0.85 * len(df_sorted))
    df_test = df_sorted.iloc[test_start:].copy()

    available = [f for f in v['features'] if f in df_test.columns]
    X_test = df_test[available].values
    y_test = df_test['consumption_mw'].values

    y_pred = v['model'].predict(X_test)
    metrics = evaluator.calculate_metrics(y_test, y_pred)
    results[name] = {'metrics': metrics, 'y_test': y_test, 'y_pred': y_pred, 'df_test': df_test}

    print(f"\\n{name.upper()}:")
    for k, val in metrics.items():
        print(f"  {k}: {val:.4f}")"""),
        md("## 3. Comparacao Visual"),
        code("""n_variants = len(results)
fig, axes = plt.subplots(1, n_variants, figsize=(7*n_variants, 5))
if n_variants == 1:
    axes = [axes]

for ax, (name, r) in zip(axes, results.items()):
    ax.scatter(r['y_test'][:2000], r['y_pred'][:2000], alpha=0.3, s=10)
    lims = [min(r['y_test'].min(), r['y_pred'].min()), max(r['y_test'].max(), r['y_pred'].max())]
    ax.plot(lims, lims, 'r--', linewidth=2)
    ax.set_xlabel('Real (MW)')
    ax.set_ylabel('Previsto (MW)')
    ax.set_title(f"{name}\\nRMSE={r['metrics']['rmse']:.2f} | MAPE={r['metrics']['mape']:.2f}%")
    ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()"""),
        md("## 4. Comparacao por Regiao"),
        code("""for name, r in results.items():
    r['df_test'] = r['df_test'].copy()
    r['df_test']['abs_error'] = np.abs(r['y_test'] - r['y_pred'])

    regional = r['df_test'].groupby('region')['abs_error'].agg(['mean', 'std']).sort_values('mean')
    print(f"\\n{name.upper()} - Erro por Regiao:")
    print(regional.to_string())"""),
        md("## 5. Tabela Comparativa"),
        code("""comparison = pd.DataFrame({
    name: {k: round(v, 4) for k, v in r['metrics'].items()}
    for name, r in results.items()
}).T

print("=" * 70)
print("TABELA COMPARATIVA")
print("=" * 70)
print(comparison.to_string())

# Baseline comparison (from metadata)
print("\\n\\nCOMPARACAO COM BASELINES (do treino):")
for name, v in variants.items():
    bc = v['meta'].get('baseline_comparison', {})
    if bc:
        best_bl = min(bc.items(), key=lambda x: x[1].get('rmse', float('inf')))
        model_rmse = v['meta']['test_metrics']['rmse']
        bl_rmse = best_bl[1].get('rmse', 0)
        improvement = (1 - model_rmse / bl_rmse) * 100 if bl_rmse > 0 else 0
        print(f"  {name}: melhor baseline={best_bl[0]} (RMSE={bl_rmse:.2f}), "
              f"modelo RMSE={model_rmse:.2f}, melhoria={improvement:.1f}%")"""),
    ]
    save(nb, "02_model_evaluation.ipynb")


# ============================================================
# NOTEBOOK 03 - Advanced Feature Analysis (load-only)
# ============================================================
def create_nb03():
    nb = nbf.v4.new_notebook()
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.cells = [
        md("""# 03 - Analise de Features Avancadas

Analise detalhada das features avancadas: correlacoes, informacao mutua,
multicolinearidade e importancia. Usa o modelo avancado pre-treinado.

**Nota:** Requer `python scripts/retrain.py` executado previamente."""),
        code("""import sys
sys.path.append('..')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import joblib
import json
import warnings

from sklearn.feature_selection import mutual_info_regression

from src.features.feature_engineering import FeatureEngineer, STANDARD_PRESSURE_HPA
from src.models.evaluation import ModelEvaluator

warnings.filterwarnings('ignore')
plt.style.use('seaborn-v0_8-darkgrid')

print(f"Pressao atmosferica padrao: {STANDARD_PRESSURE_HPA} hPa")"""),
        md("## 1. Carregar Dados e Modelo Avancado"),
        code("""df = pd.read_parquet('../data/processed/processed_data.parquet')
print(f"Dados: {len(df):,} linhas")

fe = FeatureEngineer()
df_features = fe.create_all_features(df, use_advanced=True)
print(f"Apos FE avancado: {df_features.shape[0]:,} linhas, {df_features.shape[1]} colunas")

# Carregar modelo avancado pre-treinado
models_dir = Path('../data/models')
model_path = models_dir / 'checkpoints' / 'best_model_advanced.pkl'

if model_path.exists():
    model = joblib.load(model_path)
    with open(models_dir / 'features' / 'advanced_feature_names.txt') as f:
        saved_features = [l.strip() for l in f.readlines() if l.strip()]
    with open(models_dir / 'metadata' / 'metadata_advanced.json') as f:
        meta = json.load(f)
    print(f"Modelo avancado carregado: {meta.get('best_model', 'N/A')}")
    print(f"Features do modelo: {len(saved_features)}")
else:
    print("AVISO: Modelo avancado nao encontrado. Executar 'python scripts/retrain.py' primeiro.")
    saved_features = []
    model = None

# Listar todas as features numericas
exclude_cols = ['timestamp', 'consumption_mw', 'region', 'holiday_name', 'city', 'date']
for col in df_features.columns:
    if col in exclude_cols:
        continue
    if pd.api.types.is_datetime64_any_dtype(df_features[col]) or df_features[col].dtype == 'object':
        exclude_cols.append(col)

all_features = [c for c in df_features.columns if c not in exclude_cols]
print(f"Total features numericas: {len(all_features)}")"""),
        md("## 2. Analise de Features Derivadas"),
        code("""weather_derived = ['heat_index', 'dew_point', 'comfort_index', 'effective_temperature',
                   'temp_humidity_ratio', 'wind_chill', 'pressure_relative', 'solar_proxy',
                   'precip_temp_index']

available_wd = [f for f in weather_derived if f in df_features.columns]
print("Features meteorologicas derivadas:")
for f in available_wd:
    corr = df_features[f].corr(df_features['consumption_mw'])
    print(f"  {f:30s} corr={corr:+.4f}  mean={df_features[f].mean():.2f}  std={df_features[f].std():.2f}")

trend_features = [c for c in all_features if any(x in c for x in ['diff', 'momentum', 'deviation', 'volatility'])]
print(f"\\nFeatures de tendencia: {len(trend_features)}")
for f in trend_features:
    corr = df_features[f].corr(df_features['consumption_mw'])
    print(f"  {f:30s} corr={corr:+.4f}")"""),
        md("## 3. Correlacao com Target"),
        code(
            """correlations = df_features[all_features].corrwith(df_features['consumption_mw']).abs().sort_values(ascending=False)

fig, ax = plt.subplots(figsize=(12, 10))
top30_corr = correlations.head(30)
ax.barh(range(len(top30_corr)), top30_corr.values, color='steelblue', edgecolor='black')
ax.set_yticks(range(len(top30_corr)))
ax.set_yticklabels(top30_corr.index)
ax.invert_yaxis()
ax.set_xlabel('|Correlacao| com consumo')
ax.set_title('Top 30 Features por Correlacao')
plt.tight_layout()
plt.show()

print("Top 10 features mais correlacionadas:")
for feat, corr in correlations.head(10).items():
    print(f"  {feat:40s} |r| = {corr:.4f}")"""
        ),
        md("## 4. Informacao Mutua"),
        code("""sample_size = min(50000, len(df_features))
df_sample = df_features.sample(sample_size, random_state=42)

X_sample = df_sample[all_features].fillna(0).values
y_sample = df_sample['consumption_mw'].values

mi_scores = mutual_info_regression(X_sample, y_sample, random_state=42, n_neighbors=5)
mi_df = pd.DataFrame({'feature': all_features, 'mi_score': mi_scores}).sort_values('mi_score', ascending=False)

print("Top 20 features por Informacao Mutua:")
for _, row in mi_df.head(20).iterrows():
    print(f"  {row['feature']:40s} MI = {row['mi_score']:.4f}")

fig, ax = plt.subplots(figsize=(12, 8))
top20_mi = mi_df.head(20)
ax.barh(range(len(top20_mi)), top20_mi['mi_score'].values, color='coral', edgecolor='black')
ax.set_yticks(range(len(top20_mi)))
ax.set_yticklabels(top20_mi['feature'].values)
ax.invert_yaxis()
ax.set_xlabel('Mutual Information')
ax.set_title('Top 20 Features por MI')
plt.tight_layout()
plt.show()"""),
        md("## 5. Multicolinearidade"),
        code("""non_lag_features = [f for f in all_features if 'lag' not in f and 'rolling' not in f]
corr_matrix = df_features[non_lag_features].corr()

high_corr_pairs = []
for i in range(len(corr_matrix)):
    for j in range(i+1, len(corr_matrix)):
        if abs(corr_matrix.iloc[i, j]) > 0.95:
            high_corr_pairs.append((corr_matrix.index[i], corr_matrix.columns[j], corr_matrix.iloc[i, j]))

print(f"Pares com |correlacao| > 0.95: {len(high_corr_pairs)}")
for f1, f2, corr in sorted(high_corr_pairs, key=lambda x: -abs(x[2]))[:15]:
    print(f"  {f1:35s} <-> {f2:35s} r={corr:.4f}")"""),
        md("## 6. Feature Importance do Modelo Pre-Treinado"),
        code("""if model is not None and hasattr(model, 'feature_importances_'):
    importance_df = pd.DataFrame({
        'feature': saved_features,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)

    fig, ax = plt.subplots(figsize=(12, 8))
    top20 = importance_df.head(20)
    ax.barh(range(len(top20)), top20['importance'].values, color='green', edgecolor='black')
    ax.set_yticks(range(len(top20)))
    ax.set_yticklabels(top20['feature'].values)
    ax.invert_yaxis()
    ax.set_xlabel('Feature Importance')
    ax.set_title('Top 20 Features por Importancia (Modelo Avancado)')
    plt.tight_layout()
    plt.show()

    print("\\nTop 15 features do modelo avancado:")
    for _, row in importance_df.head(15).iterrows():
        print(f"  {row['feature']:40s} importance={row['importance']:.4f}")
else:
    print("Modelo avancado nao disponivel para analise de importancia.")"""),
    ]
    save(nb, "03_advanced_feature_analysis.ipynb")


# ============================================================
# NOTEBOOK 04 - Error Analysis (load-only)
# ============================================================
def create_nb04():
    nb = nbf.v4.new_notebook()
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.cells = [
        md("""# 04 - Analise de Erros

Diagnostico detalhado dos erros do modelo para identificar fraquezas.

**Nota:** Requer `python scripts/retrain.py` executado previamente."""),
        code("""import sys
sys.path.append('..')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import joblib
import warnings
from scipy import stats

from src.features.feature_engineering import FeatureEngineer
from src.models.evaluation import ModelEvaluator

warnings.filterwarnings('ignore')
plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['figure.figsize'] = (14, 6)"""),
        md("## 1. Carregar Modelo e Dados"),
        code("""models_dir = Path('../data/models')

with open(models_dir / 'features' / 'feature_names.txt') as f:
    saved_features = [l.strip() for l in f.readlines() if l.strip()]

model = joblib.load(models_dir / 'checkpoints' / 'best_model.pkl')
print(f"Modelo carregado: best_model.pkl")
print(f"Features esperadas: {len(saved_features)}")

df = pd.read_parquet('../data/processed/processed_data.parquet')
fe = FeatureEngineer()
df_features = fe.create_all_features(df)

available_features = [f for f in saved_features if f in df_features.columns]
missing = [f for f in saved_features if f not in df_features.columns]
if missing:
    print(f"AVISO: {len(missing)} features em falta: {missing}")

print(f"Features usadas: {len(available_features)}")"""),
        md("## 2. Preparar Conjunto de Teste"),
        code("""df_sorted = df_features.sort_values('timestamp').reset_index(drop=True)
test_start = int(0.85 * len(df_sorted))
df_test = df_sorted.iloc[test_start:].copy()

X_test = df_test[available_features].values
y_test = df_test['consumption_mw'].values

y_pred = model.predict(X_test)

df_test['y_pred'] = y_pred
df_test['error'] = y_test - y_pred
df_test['abs_error'] = np.abs(df_test['error'])
df_test['pct_error'] = (df_test['error'] / y_test) * 100
df_test['abs_pct_error'] = np.abs(df_test['pct_error'])

df_test['hour'] = df_test['timestamp'].dt.hour
df_test['day_of_week'] = df_test['timestamp'].dt.dayofweek
df_test['month_val'] = df_test['timestamp'].dt.month
df_test['season'] = df_test['month_val'].map(
    lambda m: 'Inverno' if m in [12,1,2] else 'Primavera' if m in [3,4,5] else 'Verao' if m in [6,7,8] else 'Outono'
)

evaluator = ModelEvaluator()
metrics = evaluator.calculate_metrics(y_test, y_pred)
print(f"\\nMetricas globais:")
for k, v in metrics.items():
    print(f"  {k}: {v:.4f}")
print(f"  Amostras: {len(y_test):,}")"""),
        md("## 3. Erro por Regiao"),
        code("""regional = df_test.groupby('region').agg(
    mae=('abs_error', 'mean'),
    rmse=('error', lambda x: np.sqrt(np.mean(x**2))),
    mape=('abs_pct_error', 'mean'),
    count=('error', 'count')
).sort_values('mape')

print("=" * 70)
print("ERRO POR REGIAO")
print("=" * 70)
print(regional.to_string())

fig, axes = plt.subplots(1, 3, figsize=(18, 5))
regional['mae'].plot(kind='bar', ax=axes[0], color='steelblue', edgecolor='black')
axes[0].set_title('MAE por Regiao (MW)')
axes[0].set_ylabel('MAE (MW)')

regional['mape'].plot(kind='bar', ax=axes[1], color='coral', edgecolor='black')
axes[1].set_title('MAPE por Regiao (%)')
axes[1].set_ylabel('MAPE (%)')

regional['rmse'].plot(kind='bar', ax=axes[2], color='green', edgecolor='black')
axes[2].set_title('RMSE por Regiao (MW)')
axes[2].set_ylabel('RMSE (MW)')

for ax in axes:
    ax.tick_params(axis='x', rotation=45)

plt.tight_layout()
plt.show()"""),
        md("## 4. Erro por Hora"),
        code("""hourly = df_test.groupby('hour').agg(
    mae=('abs_error', 'mean'),
    mape=('abs_pct_error', 'mean')
).sort_index()

fig, axes = plt.subplots(1, 2, figsize=(16, 5))

axes[0].bar(hourly.index, hourly['mae'], color='steelblue', edgecolor='black')
axes[0].set_xlabel('Hora')
axes[0].set_ylabel('MAE (MW)')
axes[0].set_title('MAE por Hora do Dia')
axes[0].set_xticks(range(0, 24))

axes[1].bar(hourly.index, hourly['mape'], color='coral', edgecolor='black')
axes[1].set_xlabel('Hora')
axes[1].set_ylabel('MAPE (%)')
axes[1].set_title('MAPE por Hora do Dia')
axes[1].set_xticks(range(0, 24))

plt.tight_layout()
plt.show()

print(f"Pior hora (MAPE): {hourly['mape'].idxmax()}h ({hourly['mape'].max():.2f}%)")
print(f"Melhor hora (MAPE): {hourly['mape'].idxmin()}h ({hourly['mape'].min():.2f}%)")"""),
        md("## 5. Erro por Estacao"),
        code("""seasonal = df_test.groupby('season').agg(
    mae=('abs_error', 'mean'),
    mape=('abs_pct_error', 'mean'),
    count=('error', 'count')
)

print("\\nErro por Estacao:")
print(seasonal.to_string())

fig, ax = plt.subplots(figsize=(8, 5))
seasonal['mape'].plot(kind='bar', ax=ax, color='steelblue', edgecolor='black')
ax.set_ylabel('MAPE (%)')
ax.set_title('MAPE por Estacao')
ax.tick_params(axis='x', rotation=0)
plt.tight_layout()
plt.show()"""),
        md("## 6. Analise de Residuos"),
        code("""residuals = df_test['error'].values

fig, axes = plt.subplots(2, 2, figsize=(14, 10))

axes[0,0].plot(df_test['timestamp'].values[:2000], residuals[:2000], alpha=0.5, linewidth=1)
axes[0,0].axhline(0, color='red', linestyle='--')
axes[0,0].set_title('Residuos ao Longo do Tempo')
axes[0,0].set_ylabel('Residuo (MW)')

axes[0,1].hist(residuals, bins=80, edgecolor='black', alpha=0.7, density=True)
axes[0,1].axvline(0, color='red', linestyle='--')
axes[0,1].set_title('Distribuicao dos Residuos')
axes[0,1].set_xlabel('Residuo (MW)')

axes[1,0].scatter(y_pred[:5000], residuals[:5000], alpha=0.3, s=10)
axes[1,0].axhline(0, color='red', linestyle='--')
axes[1,0].set_xlabel('Valor Previsto (MW)')
axes[1,0].set_ylabel('Residuo (MW)')
axes[1,0].set_title('Residuos vs Previsao')

stats.probplot(residuals, dist="norm", plot=axes[1,1])
axes[1,1].set_title('Q-Q Plot')

plt.tight_layout()
plt.show()

print(f"\\nEstatisticas dos Residuos:")
print(f"  Media (bias):  {residuals.mean():.2f} MW")
print(f"  Desvio-padrao: {residuals.std():.2f} MW")
print(f"  Skewness:      {stats.skew(residuals):.4f}")
print(f"  Kurtosis:      {stats.kurtosis(residuals):.4f}")"""),
        md("## 7. Resumo"),
        code("""print("=" * 70)
print("RESUMO DA ANALISE DE ERROS")
print("=" * 70)
print(f\"\"\"
Metricas Globais:
  MAE:  {metrics['mae']:.2f} MW
  RMSE: {metrics['rmse']:.2f} MW
  MAPE: {metrics['mape']:.2f}%
  R2:   {metrics['r2']:.4f}

Padroes Identificados:
  - Pior regiao (MAPE): {regional['mape'].idxmax()} ({regional['mape'].max():.2f}%)
  - Melhor regiao: {regional['mape'].idxmin()} ({regional['mape'].min():.2f}%)
  - Pior hora: {hourly['mape'].idxmax()}h ({hourly['mape'].max():.2f}%)
  - Melhor hora: {hourly['mape'].idxmin()}h ({hourly['mape'].min():.2f}%)
  - Bias medio: {residuals.mean():.2f} MW (proximo de zero = bom)
\"\"\")"""),
    ]
    save(nb, "04_error_analysis.ipynb")


# ============================================================
# NOTEBOOK 05 - Robust Validation (ephemeral training, no saves)
# ============================================================
def create_nb05():
    nb = nbf.v4.new_notebook()
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.cells = [
        md(
            "# 05 - Validacao Robusta\n\nWalk-forward, backtesting sazonal e teste de estabilidade.\n\n**Nota:** Este notebook treina modelos temporarios para validacao. Nenhum modelo e salvo."
        ),
        code("""import sys
sys.path.append('..')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import warnings
from datetime import datetime

import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit

from src.features.feature_engineering import FeatureEngineer
from src.models.evaluation import ModelEvaluator

warnings.filterwarnings('ignore')
plt.style.use('seaborn-v0_8-darkgrid')
print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")"""),
        md("## 1. Preparacao"),
        code("""df = pd.read_parquet('../data/processed/processed_data.parquet')
fe = FeatureEngineer()
df_features = fe.create_all_features(df)

exclude_cols = ['timestamp', 'consumption_mw', 'region', 'holiday_name', 'city', 'date']
for col in df_features.columns:
    if col in exclude_cols:
        continue
    if pd.api.types.is_datetime64_any_dtype(df_features[col]) or df_features[col].dtype == 'object':
        exclude_cols.append(col)

features = [c for c in df_features.columns if c not in exclude_cols]

df_sorted = df_features.sort_values('timestamp').reset_index(drop=True)
X = df_sorted[features].values
y = df_sorted['consumption_mw'].values

print(f"Dados: {len(X):,} | Features: {len(features)}")"""),
        md("## 2. Walk-Forward Validation"),
        code("""N_SPLITS = 5
tscv = TimeSeriesSplit(n_splits=N_SPLITS)
evaluator = ModelEvaluator()

fold_results = []
for fold, (train_idx, test_idx) in enumerate(tscv.split(X), 1):
    model = xgb.XGBRegressor(
        n_estimators=300, max_depth=8, learning_rate=0.05,
        random_state=42, n_jobs=-1, verbosity=0
    )
    model.fit(X[train_idx], y[train_idx])
    y_pred = model.predict(X[test_idx])

    m = evaluator.calculate_metrics(y[test_idx], y_pred)
    m['fold'] = fold
    m['train_size'] = len(train_idx)
    m['test_size'] = len(test_idx)
    fold_results.append(m)

    print(f"Fold {fold}/{N_SPLITS}: MAPE={m['mape']:.2f}% R2={m['r2']:.4f} (train={len(train_idx):,} test={len(test_idx):,})")

df_folds = pd.DataFrame(fold_results)
print(f"\\nMedia: MAPE={df_folds['mape'].mean():.2f}% +/- {df_folds['mape'].std():.2f}%")
print(f"       R2={df_folds['r2'].mean():.4f} +/- {df_folds['r2'].std():.4f}")"""),
        md("## 3. Backtesting Sazonal"),
        code("""df_sorted['month_val'] = df_sorted['timestamp'].dt.month
df_sorted['season'] = df_sorted['month_val'].map(
    lambda m: 'Inverno' if m in [12,1,2] else 'Primavera' if m in [3,4,5] else 'Verao' if m in [6,7,8] else 'Outono'
)

season_results = []
for season in ['Primavera', 'Verao', 'Outono', 'Inverno']:
    mask = df_sorted['season'] == season
    df_season = df_sorted[mask].reset_index(drop=True)

    split = int(0.7 * len(df_season))
    X_train_s = df_season.iloc[:split][features].values
    y_train_s = df_season.iloc[:split]['consumption_mw'].values
    X_test_s = df_season.iloc[split:][features].values
    y_test_s = df_season.iloc[split:]['consumption_mw'].values

    model_s = xgb.XGBRegressor(
        n_estimators=300, max_depth=8, learning_rate=0.05,
        random_state=42, n_jobs=-1, verbosity=0
    )
    model_s.fit(X_train_s, y_train_s)
    y_pred_s = model_s.predict(X_test_s)

    m = evaluator.calculate_metrics(y_test_s, y_pred_s)
    m['season'] = season
    m['n_samples'] = len(X_test_s)
    season_results.append(m)

    print(f"{season:12s}: MAPE={m['mape']:.2f}% R2={m['r2']:.4f} (n={len(X_test_s):,})")

df_seasons = pd.DataFrame(season_results)"""),
        md("## 4. Estabilidade (Random Seeds)"),
        code("""stability_results = []
seeds = list(range(42, 52))

train_end = int(0.70 * len(df_sorted))
test_start = int(0.85 * len(df_sorted))
X_train_st = df_sorted.iloc[:train_end][features].values
y_train_st = df_sorted.iloc[:train_end]['consumption_mw'].values
X_test_st = df_sorted.iloc[test_start:][features].values
y_test_st = df_sorted.iloc[test_start:]['consumption_mw'].values

for seed in seeds:
    model_st = xgb.XGBRegressor(
        n_estimators=300, max_depth=8, learning_rate=0.05,
        random_state=seed, n_jobs=-1, verbosity=0
    )
    model_st.fit(X_train_st, y_train_st)
    y_pred_st = model_st.predict(X_test_st)

    m = evaluator.calculate_metrics(y_test_st, y_pred_st)
    m['seed'] = seed
    stability_results.append(m)

df_stability = pd.DataFrame(stability_results)
print(f"Estabilidade ({len(seeds)} seeds):")
print(f"  MAPE: {df_stability['mape'].mean():.3f}% +/- {df_stability['mape'].std():.5f}%")
print(f"  R2:   {df_stability['r2'].mean():.5f} +/- {df_stability['r2'].std():.6f}")
print(f"  Conclusao: {'Estavel' if df_stability['mape'].std() < 0.1 else 'Instavel'}")"""),
        md("## 5. Visualizacao"),
        code("""fig, axes = plt.subplots(1, 3, figsize=(18, 5))

axes[0].bar(range(1, N_SPLITS+1), df_folds['mape'], color='steelblue', edgecolor='black')
axes[0].set_xlabel('Fold')
axes[0].set_ylabel('MAPE (%)')
axes[0].set_title('Walk-Forward: MAPE por Fold')
axes[0].axhline(df_folds['mape'].mean(), color='red', linestyle='--', label=f"Media={df_folds['mape'].mean():.2f}%")
axes[0].legend()

axes[1].bar(df_seasons['season'], df_seasons['mape'], color='coral', edgecolor='black')
axes[1].set_ylabel('MAPE (%)')
axes[1].set_title('Backtesting Sazonal')

axes[2].plot(seeds, df_stability['mape'], 'g-o')
axes[2].set_xlabel('Random Seed')
axes[2].set_ylabel('MAPE (%)')
axes[2].set_title('Estabilidade por Seed')
axes[2].grid(True, alpha=0.3)

plt.tight_layout()
plt.show()"""),
        md("## 6. Resumo"),
        code("""print("=" * 70)
print("RESUMO DA VALIDACAO ROBUSTA")
print("=" * 70)
print(f\"\"\"
Walk-Forward ({N_SPLITS} folds):
  MAPE: {df_folds['mape'].mean():.2f}% +/- {df_folds['mape'].std():.2f}%
  R2:   {df_folds['r2'].mean():.4f} +/- {df_folds['r2'].std():.4f}
  Fold 1 vs Fold {N_SPLITS}: {df_folds.iloc[0]['mape']:.2f}% vs {df_folds.iloc[-1]['mape']:.2f}%

Backtesting Sazonal:
  Melhor: {df_seasons.loc[df_seasons['mape'].idxmin(), 'season']} ({df_seasons['mape'].min():.2f}%)
  Pior:   {df_seasons.loc[df_seasons['mape'].idxmax(), 'season']} ({df_seasons['mape'].max():.2f}%)
  Range:  {df_seasons['mape'].max() - df_seasons['mape'].min():.2f} pp

Estabilidade:
  MAPE std: {df_stability['mape'].std():.5f}% ({'Estavel' if df_stability['mape'].std() < 0.1 else 'Instavel'})
  R2 std:   {df_stability['r2'].std():.6f}
\"\"\")
print(f"Fim: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")"""),
    ]
    save(nb, "05_robust_validation.ipynb")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("Gerando notebooks de analise (5 notebooks)...")
    print("NOTA: Treino de modelos e feito via 'python scripts/retrain.py'")
    print()
    create_nb01()
    create_nb02()
    create_nb03()
    create_nb04()
    create_nb05()
    print("\nTodos os 5 notebooks gerados com sucesso!")
    print("Proximo passo: python scripts/retrain.py && python run_notebooks.py")
