# Tests - Energy Forecast PT

Testes automatizados para garantir qualidade e robustez do código.

## 📋 Estrutura

```
tests/
├── __init__.py
├── test_api.py                  # Testes da API FastAPI
├── test_feature_engineering.py  # Testes de feature engineering
└── test_models.py               # Testes de avaliação de modelos
```

## 🚀 Como Executar

### Instalar dependências de teste

```bash
pip install pytest pytest-cov httpx
```

### Executar todos os testes

```bash
# Executar todos os testes
pytest

# Com output detalhado
pytest -v

# Com cobertura de código
pytest --cov=src --cov-report=html

# Executar testes específicos
pytest tests/test_api.py
pytest tests/test_feature_engineering.py
pytest tests/test_models.py
```

### Executar teste específico

```bash
# Executar uma classe de testes
pytest tests/test_api.py::TestHealthEndpoints

# Executar um teste específico
pytest tests/test_api.py::TestHealthEndpoints::test_root_endpoint
```

## 📊 Cobertura de Testes

### test_api.py

**Cobre:**
- ✅ Health check endpoints (`/`, `/health`, `/regions`)
- ✅ Prediction endpoints (`/predict`, `/predict/batch`)
- ✅ Model info endpoints (`/model/info`, `/limitations`)
- ✅ Input validation (campos obrigatórios, tipos, ranges)
- ✅ Error handling (400, 422, 503)

**Classes:**
- `TestHealthEndpoints` - Testes de endpoints básicos
- `TestPredictionEndpoints` - Testes de previsão
- `TestModelInfo` - Testes de informação do modelo
- `TestInputValidation` - Testes de validação de input

### test_feature_engineering.py

**Cobre:**
- ✅ Criação de features temporais
- ✅ Criação de lag features
- ✅ Criação de rolling window features
- ✅ Criação de interaction features
- ✅ Pipeline completo de features
- ✅ Tratamento de edge cases (dados vazios, missing columns)
- ✅ Consistência e determinismo

**Classes:**
- `TestFeatureEngineer` - Testes principais do FeatureEngineer
- `TestFeatureConsistency` - Testes de consistência e reprodutibilidade

### test_models.py

**Cobre:**
- ✅ Cálculo de métricas (MAE, RMSE, MAPE, R²)
- ✅ Casos extremos (previsões perfeitas, com erro, com zeros)
- ✅ Validação de inputs (arrays vazios, tamanhos diferentes)
- ✅ Interpretação de métricas (modelos excelentes/bons/ruins)
- ✅ Prefixes customizados

**Classes:**
- `TestModelEvaluator` - Testes do avaliador de modelos
- `TestMetricsInterpretation` - Testes de interpretação de métricas
- `TestConfidenceIntervals` - Testes de intervalos de confiança (opcional)

## 🎯 Objetivos dos Testes

### 1. **Qualidade de Código**
- Garantir que todas as funções principais funcionam corretamente
- Prevenir regressões ao fazer mudanças
- Documentar comportamento esperado

### 2. **Robustez**
- Testar edge cases (dados vazios, valores extremos)
- Validar tratamento de erros
- Garantir consistência entre execuções

### 3. **Confiança para Deploy**
- Validar API antes de produção
- Garantir que features são criadas corretamente
- Verificar cálculo de métricas

## 📈 Melhores Práticas

### Escrevendo Novos Testes

```python
import pytest

class TestNovaFuncionalidade:
    """Testes para nova funcionalidade"""

    @pytest.fixture
    def setup_data(self):
        """Fixture para preparar dados de teste"""
        return {"key": "value"}

    def test_caso_normal(self, setup_data):
        """Testa caso normal de uso"""
        result = minha_funcao(setup_data)
        assert result == expected_value

    def test_edge_case(self):
        """Testa caso extremo"""
        with pytest.raises(ValueError):
            minha_funcao(invalid_input)
```

### Estrutura de um Teste

1. **Arrange** - Preparar dados e dependências
2. **Act** - Executar a função a ser testada
3. **Assert** - Verificar resultados

### Fixtures

Use fixtures para:
- Dados de teste reutilizáveis
- Setup/teardown de recursos
- Mocks de dependências externas

## 🔧 Configuração

### pytest.ini (opcional)

Criar arquivo `pytest.ini` na raiz do projeto:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --strict-markers
markers =
    slow: marks tests as slow
    integration: marks tests as integration tests
```

### CI/CD Integration

Os testes já estão integrados no GitHub Actions (`.github/workflows/ci-cd.yml`):

```yaml
- name: Run tests
  run: pytest --cov=src --cov-report=xml
```

## 📝 TODO - Testes Futuros

- [ ] Testes de integração completos (API + Feature Engineering + Models)
- [ ] Testes de performance (latência, throughput)
- [ ] Testes de carga (stress testing)
- [ ] Testes de regressão visual
- [ ] Property-based testing (Hypothesis)
- [ ] Mutation testing (verificar qualidade dos testes)

## 🐛 Debugging Testes

### Executar com pdb

```bash
pytest --pdb  # Para no primeiro erro
pytest -x     # Para após primeiro falha
```

### Ver print statements

```bash
pytest -s  # Mostra prints
```

### Executar apenas testes que falharam

```bash
pytest --lf  # last-failed
pytest --ff  # failed-first
```

## 📚 Recursos

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Coverage.py](https://coverage.readthedocs.io/)

---

**Nota:** Alguns testes podem falhar se os modelos não estiverem treinados. Execute os notebooks de treino primeiro ou os testes irão retornar status 503 (Service Unavailable).
