"""
Métricas de avaliação para modelos de time series
"""

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from typing import Tuple, Dict
import pandas as pd


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """
    Calcular múltiplas métricas de avaliação

    Args:
        y_true: valores reais
        y_pred: valores previstos

    Returns:
        Dicionário com métricas
    """
    # Remover NaN
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true = y_true[mask]
    y_pred = y_pred[mask]

    metrics = {}

    # MAE - Mean Absolute Error
    metrics['mae'] = mean_absolute_error(y_true, y_pred)

    # RMSE - Root Mean Squared Error
    metrics['rmse'] = np.sqrt(mean_squared_error(y_true, y_pred))

    # MAPE - Mean Absolute Percentage Error
    # Evitar divisão por zero
    mask_nonzero = y_true != 0
    if mask_nonzero.sum() > 0:
        mape = np.mean(np.abs((y_true[mask_nonzero] - y_pred[mask_nonzero]) / y_true[mask_nonzero])) * 100
        metrics['mape'] = mape
    else:
        metrics['mape'] = np.nan

    # R² Score
    metrics['r2'] = r2_score(y_true, y_pred)

    # Normalized RMSE (NRMSE) - normalizado pela média
    mean_true = y_true.mean()
    if mean_true != 0:
        metrics['nrmse'] = metrics['rmse'] / mean_true
    else:
        metrics['nrmse'] = np.nan

    return metrics


def calculate_coverage(
    y_true: np.ndarray,
    y_pred_lower: np.ndarray,
    y_pred_upper: np.ndarray,
    confidence_level: float = 0.90
) -> float:
    """
    Calcular cobertura do intervalo de previsão

    Args:
        y_true: valores reais
        y_pred_lower: limite inferior do intervalo
        y_pred_upper: limite superior do intervalo
        confidence_level: nível de confiança esperado

    Returns:
        Cobertura real (proporção de valores dentro do intervalo)
    """
    within_interval = (y_true >= y_pred_lower) & (y_true <= y_pred_upper)
    coverage = within_interval.mean()

    return coverage


def mean_absolute_scaled_error(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_train: np.ndarray,
    seasonality: int = 24
) -> float:
    """
    MASE - Mean Absolute Scaled Error

    Métrica que compara o erro com um baseline sazonal
    Útil para comparar modelos em diferentes escalas

    Args:
        y_true: valores reais (test set)
        y_pred: valores previstos
        y_train: valores de treino (para calcular baseline)
        seasonality: período de sazonalidade (24h para dados horários)

    Returns:
        MASE score
    """
    # MAE do modelo
    mae_model = mean_absolute_error(y_true, y_pred)

    # MAE do baseline naive sazonal
    naive_forecast = y_train[:-seasonality]
    naive_actual = y_train[seasonality:]
    mae_naive = mean_absolute_error(naive_actual, naive_forecast)

    # MASE
    if mae_naive == 0:
        return np.nan

    mase = mae_model / mae_naive

    return mase


def calculate_residual_stats(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """
    Calcular estatísticas dos resíduos

    Args:
        y_true: valores reais
        y_pred: valores previstos

    Returns:
        Estatísticas dos resíduos
    """
    residuals = y_true - y_pred

    stats = {
        'residual_mean': np.mean(residuals),
        'residual_std': np.std(residuals),
        'residual_min': np.min(residuals),
        'residual_max': np.max(residuals),
        'residual_q25': np.percentile(residuals, 25),
        'residual_median': np.median(residuals),
        'residual_q75': np.percentile(residuals, 75),
    }

    return stats


def print_metrics(metrics: Dict[str, float], title: str = "Model Metrics"):
    """
    Imprimir métricas formatadas

    Args:
        metrics: dicionário de métricas
        title: título para impressão
    """
    print("\n" + "="*50)
    print(f"{title:^50}")
    print("="*50)

    for metric_name, value in metrics.items():
        if isinstance(value, float):
            print(f"{metric_name:20s}: {value:>10.4f}")
        else:
            print(f"{metric_name:20s}: {value:>10}")

    print("="*50 + "\n")


if __name__ == "__main__":
    # Teste
    y_true = np.array([100, 150, 200, 250, 300])
    y_pred = np.array([105, 145, 210, 240, 295])

    metrics = calculate_metrics(y_true, y_pred)
    print_metrics(metrics)
