# Tests - Energy Forecast PT

Testes automatizados para garantir qualidade e robustez do codigo.

## Estrutura

```
tests/
├── conftest.py                    # Fixtures partilhadas (app state, rate limiter, dados)
├── test_api.py                    # Testes da API FastAPI
├── test_api_extended.py           # Testes API adicionais
├── test_api_regions_and_errors.py # Regioes e tratamento de erros
├── test_feature_engineering.py    # Testes de feature engineering
├── test_models.py                 # Testes de avaliacao de modelos
├── test_model_registry.py         # Testes do registo de modelos
├── test_metrics_extended.py       # Testes de metricas estendidos
├── test_evaluation_extended.py    # Avaliacao estendida
├── test_conformal.py              # Testes de conformal prediction
├── test_metadata.py               # Testes de metadados
├── test_new_features.py           # Testes v2.0 (middleware, coverage)
├── test_rate_limit.py             # Testes de rate limiting
├── test_integration.py            # Testes de integracao basicos
├── test_full_integration.py       # Testes de integracao end-to-end completos
├── test_smoke.py                  # Smoke tests
├── test_edge_cases.py             # Casos extremos
├── test_coverage_gaps.py          # Cobertura de caminhos pouco testados
├── test_coverage_boost.py         # Boost de cobertura
├── test_performance.py            # Testes de performance (benchmark)
├── test_retrain_script.py         # Testes do script de retrain
├── test_load.py                   # Testes de carga (latencia, throughput)
├── test_stress.py                 # Testes de stress (limites do sistema)
├── test_property_based.py         # Property-based testing (Hypothesis)
└── README.md
```

## Como Executar

```bash
# Instalar dependencias
pip install -r requirements-dev.txt

# Todos os testes
pytest

# Com cobertura
pytest --cov=src --cov-report=html

# Por categoria (usando markers)
pytest -m integration          # Testes de integracao
pytest -m load                 # Testes de carga
pytest -m stress               # Testes de stress
pytest -m property_based       # Property-based tests

# Testes rapidos (excluir lentos)
pytest -m "not slow and not stress and not load"

# Testes especificos
pytest tests/test_api.py -v
pytest tests/test_full_integration.py -v
```

## Categorias de Testes

### Unitarios
- `test_models.py` - Calculo de metricas (MAE, RMSE, MAPE, R2)
- `test_metrics_extended.py` - Metricas adicionais e edge cases
- `test_feature_engineering.py` - Criacao de features
- `test_model_registry.py` - Criacao e treino de modelos
- `test_conformal.py` - Conformal prediction
- `test_metadata.py` - Serializacao de metadados

### API
- `test_api.py` - Endpoints basicos
- `test_api_extended.py` - Endpoints avancados
- `test_api_regions_and_errors.py` - Regioes e erros
- `test_rate_limit.py` - Rate limiting
- `test_new_features.py` - Features v2.0

### Integracao
- `test_integration.py` - Integracao basica
- `test_full_integration.py` - End-to-end completo (feature eng -> treino -> API)

### Performance
- `test_performance.py` - Benchmarks com pytest-benchmark
- `test_load.py` - Latencia, throughput, concorrencia
- `test_stress.py` - Limites do sistema, recuperacao de erros

### Property-Based
- `test_property_based.py` - Testes com Hypothesis (propriedades matematicas)

### Mutation Testing
```bash
# Executar mutation testing
bash scripts/run_mutation_tests.sh

# Ou manualmente
mutmut run --paths-to-mutate=src/utils/metrics.py
mutmut results
mutmut html
```

## Frontend Tests

```bash
cd frontend

# Instalar dependencias de teste
npm install

# Executar testes
npm test

# Com cobertura
npm run test:coverage

# Watch mode (desenvolvimento)
npm run test:watch
```

## CI/CD

Os testes estao integrados no GitHub Actions (`.github/workflows/ci-cd.yml`):
- pytest com cobertura minima de 85%
- Lint (black, isort, ruff)
- Type checking (mypy)
- Security (pip-audit, bandit)

## Markers

```ini
[pytest]
markers =
    slow: testes lentos (> 5s)
    integration: testes de integracao
    load: testes de carga
    stress: testes de stress
    property_based: property-based testing
```
