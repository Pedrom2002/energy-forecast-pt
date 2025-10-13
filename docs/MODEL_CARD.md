# Model Card: Energy Consumption Forecasting for Portugal

## Model Details

**Model Name:** Energy Forecast PT - XGBoost Ensemble
**Model Version:** 1.0
**Model Date:** October 2024
**Model Type:** Gradient Boosting Regression (XGBoost)
**License:** MIT

### Model Description

Sistema de previsão de consumo energético horário para Portugal, segmentado por região. O modelo utiliza XGBoost (Extreme Gradient Boosting) com feature engineering avançado incluindo lags temporais, rolling windows, e features meteorológicas derivadas.

**Desenvolvido por:** Pedro Marques

---

## Intended Use

### Primary Use Cases

1. **Previsão Operacional** - Forecasting de curto prazo (1-24h) para operadores de rede elétrica
2. **Planeamento de Carga** - Otimização de distribuição energética por região
3. **Análise de Padrões** - Identificação de padrões de consumo e sazonalidade
4. **Demonstração Técnica** - Portfolio de Data Science e ML Engineering



## Training Data

### Dataset

**Source:** Dados ficticios de consumo energético e meteorológicos de Portugal]
**Granularity:** Horária (hourly)
**Size:** 174,965 amostras de treino (~99.9% retenção após feature engineering)

### Regions Covered

1. Alentejo
2. Algarve
3. Centro
4. Lisboa
5. Norte

### Features (68 total)

#### 1. Temporal Features (6)
- `hour` (0-23)
- `day_of_week` (0-6)
- `month` (1-12)
- `quarter` (1-4)
- `year`
- `is_holiday` (binary)

#### 2. Weather Features (6)
- `temperature` (°C)
- `humidity` (%)
- `wind_speed` (km/h)
- `precipitation` (mm)
- `cloud_cover` (%)
- `pressure` (hPa)

#### 3. Lag Features (7)
Valores históricos de consumo:
- `lag_1h`, `lag_2h`, `lag_3h`
- `lag_6h`, `lag_12h`
- `lag_24h`, `lag_48h`

#### 4. Rolling Window Features (10)
Estatísticas móveis:
- `rolling_mean_3h`, `rolling_mean_6h`, `rolling_mean_12h`, `rolling_mean_24h`, `rolling_mean_48h`
- `rolling_std_3h`, `rolling_std_6h`, `rolling_std_12h`, `rolling_std_24h`, `rolling_std_48h`

#### 5. Interaction Features (15+)
Combinações entre features temporais e meteorológicas:
- `hour_x_temperature`
- `temperature_x_humidity`
- `wind_speed_x_cloud_cover`
- etc.

#### 6. Advanced Weather Features (opcional)
- Heat Index
- Wind Chill
- Dew Point
- Apparent Temperature

### Data Split

**Temporal split** (sem shuffling para preservar ordem temporal):
- **Training:** 70% (primeiros 70% cronologicamente)
- **Validation:** 15% (15% seguintes)
- **Test:** 15% (últimos 15%)

**Justificação:** Split temporal previne data leakage e simula condições de produção onde previsões são feitas para o futuro.

---

## Model Architecture

### Algorithm

**XGBoost (Extreme Gradient Boosting)** - Escolhido após comparação com:
- Random Forest
- LightGBM
- CatBoost

**Razão:** Melhor balanço entre performance (MAPE 0.86%) e velocidade de inferência.

### Hyperparameters (Optimized via Optuna)

```python
{
  'n_estimators': 300-500,
  'max_depth': 6-10,
  'learning_rate': 0.03-0.1,
  'subsample': 0.7-0.9,
  'colsample_bytree': 0.7-0.9,
  'min_child_weight': 1-5,
  'reg_alpha': 0-1,
  'reg_lambda': 0-1,
  'random_state': 42
}
```

**Optimization Method:** Optuna TPE Sampler + MedianPruner
**Trials:** 20 (optimized for speed)
**Cross-Validation:** TimeSeriesSplit (2 folds)

### Ensemble Methods 

Modelo suporta ensemble via:
1. **Stacking** - Meta-learner Ridge combinando XGBoost, LightGBM, CatBoost
2. **Weighted Averaging** - Pesos baseados em RMSE no validation set
3. **Simple Averaging** - Média aritmética de previsões

---

## Performance

### Test Set Metrics

| Metric | Value | Interpretation |
|--------|-------|----------------|
| **MAE** | 10.65 MW | Erro médio de ~11 MW |
| **RMSE** | 20.25 MW | Raiz do erro quadrático médio |
| **MAPE** | **0.86%** | ⭐ Excelente precisão (<1%) |
| **R²** | **0.9995** | Explica 99.95% da variância |
| **NRMSE** | ~0.4% | Normalizado pela média |

### Performance Interpretation

**MAPE 0.86%** significa:
- Para consumo de 2500 MW → erro médio de **±21.5 MW**
- Para consumo de 1500 MW → erro médio de **±12.9 MW**

### Confidence Intervals

Intervalos de confiança 95% calibrados:
- **Coverage:** 93.1% (próximo do ideal 95%)
- **Width:** ±66 MW em média

### Performance by Region

| Region | MAPE | Notes |
|--------|------|-------|
| Lisboa | 0.82% | Melhor performance (mais dados) |
| Porto/Norte | 0.88% | Boa performance |
| Centro | 0.90% | Boa performance |
| Algarve | 0.95% | Menor volume de dados |
| Alentejo | 0.92% | Menor volume de dados |

### Performance by Time

- **Weekdays:** MAPE 0.84% (melhor)
- **Weekends:** MAPE 0.92% (padrões diferentes)
- **Peak hours (9-18h):** MAPE 0.80%
- **Off-peak hours:** MAPE 0.95%

### Model Stability

**Stability Test (10 seeds):**
- MAPE: 0.86% ± 0.03% (baixa variância ✅)
- R²: 0.9995 ± 0.00002

**Walk-Forward Validation (5 folds):**
- MAPE: 0.88% ± 0.12%
- Modelo estável ao longo do tempo

---

## Limitations

### 1. **Dependência de Dados Históricos** ⚠️

**Modelo COM Lags (xgboost_best.pkl):**
- Requer **48h de histórico de consumo**
- Sem histórico → usar modelo alternativo (xgboost_no_lags.pkl)
- Performance degrada sem lags (MAPE ~3-8%)

### 2. **Scope Geográfico**

- Treinado apenas para **5 regiões de Portugal**
- Não generaliza para outros países/regiões
- Performance pode variar em regiões com menos dados

### 3. **Horizonte Temporal**

- Otimizado para **1-24h à frente**
- Performance degrada após 24h
- Não recomendado para >48h sem re-treino

### 4. **Covariate Shift**

- Performance pode degradar se distribuição de dados mudar:
  - Eventos extremos (ondas de calor, tempestades)
  - Mudanças estruturais (novos padrões de consumo)
  - Alterações climáticas de longo prazo
- **Recomendação:** Monitorar métricas e re-treinar periodicamente

### 5. **Feature Availability**

- Requer dados meteorológicos em tempo real
- Qualidade das previsões depende da qualidade dos inputs
- Missing data pode impactar performance

### 6. **Eventos Especiais**

- Feriados modelados, mas eventos únicos podem ter erro maior:
  - Eventos desportivos nacionais
  - Greves de energia
  - Blackouts regionais

### 7. **Interpretabilidade**

- Modelo de ensemble é complexo
- Feature importance disponível, mas causalidade não garantida
- Não substitui análise de especialistas de domínio

---

## Ethical Considerations

### Fairness

- **Balanceamento Regional:** Modelo pode ter viés para Lisboa/Porto (mais dados)
- **Equidade:** Todas as regiões têm cobertura, mas performance varia
- **Mitigação:** Documentar diferenças e ajustar thresholds por região se necessário

### Privacy

- ✅ Dados agregados por região (não identificam indivíduos)
- ✅ Sem PII (Personally Identifiable Information)
- ✅ Apenas consumo agregado e meteorologia pública

### Environmental Impact

**Carbon Footprint:**
- Training: ~2-3 horas em CPU (energia reduzida)
- Inference: <10ms por previsão (muito eficiente)
- Model size: ~50-100MB (compacto)

**Positive Impact:**
- Otimização de rede → redução de desperdício energético
- Melhor planeamento → menos dependência de fontes poluentes

### Transparency

- ✅ Código open-source (MIT License)
- ✅ Feature importance documentada
- ✅ Métricas públicas e reproduzíveis
- ✅ Limitações claramente documentadas

---

## Recommendations

### Operational Use

1. **Monitoring:**
   - Monitorar MAPE diário
   - Alertar se MAPE > 2% (degradação)
   - Track covariate shift (distribuição de features)

2. **Retraining:**
   - Re-treinar mensalmente com novos dados
   - Re-avaliar hiperparâmetros trimestralmente
   - Validar performance após mudanças estruturais

3. **Fallback:**
   - Manter modelo SEM lags como backup
   - Implementar regras de negócio para casos extremos
   - Validação humana para decisões críticas

4. **Input Validation:**
   - Validar ranges de features (temperatura, humidade, etc.)
   - Rejeitar inputs fora de distribuição de treino
   - Log de inputs suspeitos para análise

### Future Improvements

1. **Model Enhancements:**
   - Adicionar features de preços de energia
   - Incluir dados de eventos (calendário desportivo)
   - Testar deep learning (LSTM, Transformers)

2. **Infrastructure:**
   - Implementar A/B testing framework
   - Adicionar model versioning (MLflow)
   - Automated retraining pipeline

3. **Monitoring:**
   - Data drift detection automático
   - Model explainability (SHAP values)
   - Dashboards de performance em tempo real

4. **Coverage:**
   - Expandir para mais regiões
   - Adicionar previsões probabilísticas
   - Multi-horizon forecasting simultâneo

---

## Model Card Authors

**Primary Author:** [Seu Nome]
**Contributors:** Energy Forecast PT Team
**Last Updated:** January 2025
**Version:** 1.0

---

## Citation

```bibtex
@misc{energy_forecast_pt_2025,
  title={Energy Consumption Forecasting for Portugal using XGBoost},
  author={[Seu Nome]},
  year={2025},
  url={https://github.com/[seu-username]/energy-forecast-pt}
}
```

---

## Appendix

### Model Files

- `xgboost_best.pkl` - Modelo COM lags (MAPE 0.86%)
- `xgboost_no_lags.pkl` - Modelo SEM lags (MAPE ~3-8%)
- `xgboost_optimized.pkl` - Modelo otimizado (após tuning)
- `ensemble_stacking.pkl` - Ensemble de modelos (opcional)
- `feature_names.txt` - Lista de features
- `training_metadata.json` - Metadados de treino

### References

1. Chen, T., & Guestrin, C. (2016). XGBoost: A Scalable Tree Boosting System. KDD '16.
2. Hong, T., et al. (2016). Probabilistic energy forecasting: Global Energy Forecasting Competition 2014.
3. Time Series Cross-Validation: scikit-learn TimeSeriesSplit documentation

### Contact

Para questões, bugs ou contribuições:
- **GitHub:** [Link do repositório]
- **Email:** [Seu email]
- **Issues:** [Link para issues]

---

**Disclaimer:** Este modelo é fornecido "as is" para fins demonstrativos e educacionais. Para uso em produção, recomenda-se validação adicional e monitoramento contínuo.
