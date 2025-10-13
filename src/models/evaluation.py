"""
Model Evaluation Module

Contains comprehensive evaluation tools for time series forecasting models,
including metrics calculation, cross-validation, and visualization.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple, Optional, Any
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, mean_absolute_percentage_error
from sklearn.model_selection import TimeSeriesSplit
from pathlib import Path
import joblib


class ModelEvaluator:
    """
    Comprehensive model evaluation for time series forecasting

    Features:
    - Multiple metrics (MAE, RMSE, MAPE, R2)
    - Time series cross-validation
    - Prediction visualization
    - Residual analysis
    - Prediction interval coverage

    Example:
        evaluator = ModelEvaluator()
        metrics = evaluator.calculate_metrics(y_true, y_pred)
        evaluator.plot_predictions(y_true, y_pred, timestamps)
    """

    def __init__(self, output_dir: str = "outputs/evaluation"):
        """
        Initialize ModelEvaluator

        Args:
            output_dir: Directory to save plots and results
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Set style for plots
        plt.style.use('seaborn-v0_8-darkgrid')
        sns.set_palette("husl")

    def calculate_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        prefix: str = ""
    ) -> Dict[str, float]:
        """
        Calculate comprehensive evaluation metrics

        Args:
            y_true: True values
            y_pred: Predicted values
            prefix: Prefix for metric names (e.g., 'train_', 'test_')

        Returns:
            Dictionary with metrics: MAE, RMSE, MAPE, R2, NRMSE
        """
        # Check for empty arrays first
        if len(y_true) == 0 or len(y_pred) == 0:
            raise ValueError("Cannot calculate metrics for empty arrays")

        # Remove NaN values
        mask = ~(np.isnan(y_true) | np.isnan(y_pred))
        y_true_clean = y_true[mask]
        y_pred_clean = y_pred[mask]

        if len(y_true_clean) == 0:
            raise ValueError("No valid values remaining after removing NaN")

        metrics = {}

        # MAE - Mean Absolute Error
        metrics[f'{prefix}mae'] = mean_absolute_error(y_true_clean, y_pred_clean)

        # RMSE - Root Mean Squared Error
        metrics[f'{prefix}rmse'] = np.sqrt(mean_squared_error(y_true_clean, y_pred_clean))

        # MAPE - Mean Absolute Percentage Error
        try:
            # Avoid division by zero
            mask_nonzero = y_true_clean != 0
            if mask_nonzero.sum() > 0:
                mape = np.mean(np.abs((y_true_clean[mask_nonzero] - y_pred_clean[mask_nonzero])
                                     / y_true_clean[mask_nonzero])) * 100
                metrics[f'{prefix}mape'] = mape
            else:
                metrics[f'{prefix}mape'] = np.nan
        except:
            metrics[f'{prefix}mape'] = np.nan

        # R2 Score
        metrics[f'{prefix}r2'] = r2_score(y_true_clean, y_pred_clean)

        # NRMSE - Normalized RMSE (by mean)
        mean_true = y_true_clean.mean()
        if mean_true != 0:
            metrics[f'{prefix}nrmse'] = metrics[f'{prefix}rmse'] / mean_true
        else:
            metrics[f'{prefix}nrmse'] = np.nan

        return metrics

    def time_series_cross_validation(
        self,
        model: Any,
        X: np.ndarray,
        y: np.ndarray,
        n_splits: int = 5,
        test_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Perform time series cross-validation

        Uses TimeSeriesSplit to respect temporal order and avoid data leakage.

        Args:
            model: Sklearn-compatible model with fit() and predict() methods
            X: Feature matrix
            y: Target vector
            n_splits: Number of splits for cross-validation
            test_size: Size of test set in each split (if None, auto-determined)

        Returns:
            Dictionary with:
                - 'metrics': List of metrics for each fold
                - 'avg_metrics': Average metrics across folds
                - 'std_metrics': Standard deviation of metrics
        """
        tscv = TimeSeriesSplit(n_splits=n_splits, test_size=test_size)

        fold_metrics = []
        predictions = []
        actuals = []

        print(f"Performing {n_splits}-fold time series cross-validation...")

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X), 1):
            # Split data
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            # Train model
            model.fit(X_train, y_train)

            # Predict
            y_pred = model.predict(X_test)

            # Calculate metrics
            metrics = self.calculate_metrics(y_test, y_pred, prefix=f'fold{fold}_')
            fold_metrics.append(metrics)

            # Store predictions
            predictions.extend(y_pred)
            actuals.extend(y_test)

            print(f"  Fold {fold}/{n_splits} - MAE: {metrics[f'fold{fold}_mae']:.2f}, "
                  f"RMSE: {metrics[f'fold{fold}_rmse']:.2f}, "
                  f"MAPE: {metrics[f'fold{fold}_mape']:.2f}%")

        # Calculate aggregate metrics
        metrics_df = pd.DataFrame(fold_metrics)

        # Remove fold prefix for aggregation
        clean_metrics = {}
        for col in metrics_df.columns:
            clean_col = col.split('_', 1)[1] if '_' in col else col
            if clean_col not in clean_metrics:
                clean_metrics[clean_col] = []
            clean_metrics[clean_col].append(metrics_df[col].values[0])

        clean_metrics_df = pd.DataFrame(clean_metrics)

        avg_metrics = {f'avg_{k}': v for k, v in clean_metrics_df.mean().to_dict().items()}
        std_metrics = {f'std_{k}': v for k, v in clean_metrics_df.std().to_dict().items()}

        print("\nCross-Validation Results:")
        print(f"  Average MAE: {avg_metrics['avg_mae']:.2f} +/- {std_metrics['std_mae']:.2f}")
        print(f"  Average RMSE: {avg_metrics['avg_rmse']:.2f} +/- {std_metrics['std_rmse']:.2f}")
        print(f"  Average MAPE: {avg_metrics['avg_mape']:.2f}% +/- {std_metrics['std_mape']:.2f}%")
        print(f"  Average R2: {avg_metrics['avg_r2']:.4f} +/- {std_metrics['std_r2']:.4f}")

        return {
            'fold_metrics': fold_metrics,
            'avg_metrics': avg_metrics,
            'std_metrics': std_metrics,
            'predictions': np.array(predictions),
            'actuals': np.array(actuals)
        }

    def plot_predictions(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        timestamps: Optional[pd.DatetimeIndex] = None,
        title: str = "Predictions vs Actual",
        save_name: Optional[str] = None,
        max_points: int = 1000
    ) -> plt.Figure:
        """
        Plot predictions against actual values

        Args:
            y_true: True values
            y_pred: Predicted values
            timestamps: Optional timestamps for x-axis
            title: Plot title
            save_name: If provided, save plot to file
            max_points: Maximum points to plot (for performance)

        Returns:
            Matplotlib figure
        """
        # Sample data if too large
        if len(y_true) > max_points:
            indices = np.linspace(0, len(y_true) - 1, max_points, dtype=int)
            y_true = y_true[indices]
            y_pred = y_pred[indices]
            if timestamps is not None:
                # Convert to numpy array first, then index
                timestamps = timestamps.values[indices] if hasattr(timestamps, 'values') else timestamps[indices]

        fig, axes = plt.subplots(2, 1, figsize=(15, 10))

        # Time series plot
        x = timestamps if timestamps is not None else np.arange(len(y_true))

        axes[0].plot(x, y_true, label='Actual', alpha=0.7, linewidth=1.5)
        axes[0].plot(x, y_pred, label='Predicted', alpha=0.7, linewidth=1.5)
        axes[0].set_xlabel('Time' if timestamps is not None else 'Sample')
        axes[0].set_ylabel('Energy Consumption (MW)')
        axes[0].set_title(title)
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        # Scatter plot
        axes[1].scatter(y_true, y_pred, alpha=0.5, s=20)

        # Perfect prediction line
        min_val = min(y_true.min(), y_pred.min())
        max_val = max(y_true.max(), y_pred.max())
        axes[1].plot([min_val, max_val], [min_val, max_val], 'r--',
                    label='Perfect Prediction', linewidth=2)

        axes[1].set_xlabel('Actual (MW)')
        axes[1].set_ylabel('Predicted (MW)')
        axes[1].set_title('Predicted vs Actual Scatter')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)

        # Add metrics as text
        metrics = self.calculate_metrics(y_true, y_pred)
        metrics_text = (f"MAE: {metrics['mae']:.2f}\n"
                       f"RMSE: {metrics['rmse']:.2f}\n"
                       f"MAPE: {metrics['mape']:.2f}%\n"
                       f"R²: {metrics['r2']:.4f}")

        axes[1].text(0.05, 0.95, metrics_text,
                    transform=axes[1].transAxes,
                    verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        plt.tight_layout()

        if save_name:
            save_path = self.output_dir / save_name
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to {save_path}")

        return fig

    def plot_residuals(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        timestamps: Optional[pd.DatetimeIndex] = None,
        title: str = "Residual Analysis",
        save_name: Optional[str] = None
    ) -> plt.Figure:
        """
        Plot residual analysis

        Args:
            y_true: True values
            y_pred: Predicted values
            timestamps: Optional timestamps
            title: Plot title
            save_name: If provided, save plot to file

        Returns:
            Matplotlib figure
        """
        residuals = y_true - y_pred

        fig, axes = plt.subplots(2, 2, figsize=(15, 10))

        # Residuals over time
        x = timestamps if timestamps is not None else np.arange(len(residuals))
        axes[0, 0].plot(x, residuals, alpha=0.5, linewidth=1)
        axes[0, 0].axhline(y=0, color='r', linestyle='--', linewidth=2)
        axes[0, 0].set_xlabel('Time' if timestamps is not None else 'Sample')
        axes[0, 0].set_ylabel('Residuals (MW)')
        axes[0, 0].set_title('Residuals Over Time')
        axes[0, 0].grid(True, alpha=0.3)

        # Residuals distribution
        axes[0, 1].hist(residuals, bins=50, edgecolor='black', alpha=0.7)
        axes[0, 1].axvline(x=0, color='r', linestyle='--', linewidth=2)
        axes[0, 1].set_xlabel('Residuals (MW)')
        axes[0, 1].set_ylabel('Frequency')
        axes[0, 1].set_title('Residuals Distribution')
        axes[0, 1].grid(True, alpha=0.3)

        # Residuals vs Predicted
        axes[1, 0].scatter(y_pred, residuals, alpha=0.5, s=20)
        axes[1, 0].axhline(y=0, color='r', linestyle='--', linewidth=2)
        axes[1, 0].set_xlabel('Predicted Values (MW)')
        axes[1, 0].set_ylabel('Residuals (MW)')
        axes[1, 0].set_title('Residuals vs Predicted')
        axes[1, 0].grid(True, alpha=0.3)

        # Q-Q plot
        from scipy import stats
        stats.probplot(residuals, dist="norm", plot=axes[1, 1])
        axes[1, 1].set_title('Q-Q Plot')
        axes[1, 1].grid(True, alpha=0.3)

        # Add statistics
        stats_text = (f"Mean: {residuals.mean():.2f}\n"
                     f"Std: {residuals.std():.2f}\n"
                     f"Min: {residuals.min():.2f}\n"
                     f"Max: {residuals.max():.2f}")

        axes[0, 1].text(0.05, 0.95, stats_text,
                       transform=axes[0, 1].transAxes,
                       verticalalignment='top',
                       bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        fig.suptitle(title, fontsize=16, y=1.00)
        plt.tight_layout()

        if save_name:
            save_path = self.output_dir / save_name
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to {save_path}")

        return fig

    def calculate_coverage(
        self,
        y_true: np.ndarray,
        y_pred_lower: np.ndarray,
        y_pred_upper: np.ndarray,
        confidence_level: float = 0.90
    ) -> Dict[str, float]:
        """
        Calculate prediction interval coverage

        Evaluates how well prediction intervals capture actual values.

        Args:
            y_true: True values
            y_pred_lower: Lower bound of prediction interval
            y_pred_upper: Upper bound of prediction interval
            confidence_level: Expected confidence level (e.g., 0.90 for 90%)

        Returns:
            Dictionary with coverage metrics:
                - coverage: Actual coverage (proportion of values in interval)
                - expected_coverage: Expected coverage (confidence level)
                - coverage_error: Difference between actual and expected
                - interval_width_mean: Average interval width
                - interval_width_std: Std of interval width
        """
        # Remove NaN values
        mask = ~(np.isnan(y_true) | np.isnan(y_pred_lower) | np.isnan(y_pred_upper))
        y_true_clean = y_true[mask]
        y_pred_lower_clean = y_pred_lower[mask]
        y_pred_upper_clean = y_pred_upper[mask]

        # Calculate coverage
        within_interval = (y_true_clean >= y_pred_lower_clean) & (y_true_clean <= y_pred_upper_clean)
        actual_coverage = within_interval.mean()

        # Calculate interval widths
        interval_widths = y_pred_upper_clean - y_pred_lower_clean

        results = {
            'coverage': actual_coverage,
            'expected_coverage': confidence_level,
            'coverage_error': actual_coverage - confidence_level,
            'interval_width_mean': interval_widths.mean(),
            'interval_width_std': interval_widths.std(),
            'interval_width_min': interval_widths.min(),
            'interval_width_max': interval_widths.max(),
            'n_samples': len(y_true_clean),
            'n_within_interval': within_interval.sum()
        }

        print(f"\nPrediction Interval Coverage Analysis:")
        print(f"  Expected Coverage: {confidence_level*100:.1f}%")
        print(f"  Actual Coverage: {actual_coverage*100:.1f}%")
        print(f"  Coverage Error: {results['coverage_error']*100:.1f}%")
        print(f"  Average Interval Width: {results['interval_width_mean']:.2f} MW")

        return results

    def plot_prediction_intervals(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_pred_lower: np.ndarray,
        y_pred_upper: np.ndarray,
        timestamps: Optional[pd.DatetimeIndex] = None,
        title: str = "Prediction Intervals",
        save_name: Optional[str] = None,
        max_points: int = 500
    ) -> plt.Figure:
        """
        Plot prediction intervals

        Args:
            y_true: True values
            y_pred: Predicted values
            y_pred_lower: Lower bound
            y_pred_upper: Upper bound
            timestamps: Optional timestamps
            title: Plot title
            save_name: If provided, save plot to file
            max_points: Maximum points to plot

        Returns:
            Matplotlib figure
        """
        # Sample data if too large
        if len(y_true) > max_points:
            indices = np.linspace(0, len(y_true) - 1, max_points, dtype=int)
            y_true = y_true[indices]
            y_pred = y_pred[indices]
            y_pred_lower = y_pred_lower[indices]
            y_pred_upper = y_pred_upper[indices]
            if timestamps is not None:
                # Convert to numpy array first, then index
                timestamps = timestamps.values[indices] if hasattr(timestamps, 'values') else timestamps[indices]

        fig, ax = plt.subplots(figsize=(15, 6))

        x = timestamps if timestamps is not None else np.arange(len(y_true))

        # Plot actual values
        ax.plot(x, y_true, label='Actual', color='black', alpha=0.7, linewidth=2)

        # Plot predictions
        ax.plot(x, y_pred, label='Predicted', color='blue', alpha=0.7, linewidth=2)

        # Plot prediction intervals
        ax.fill_between(x, y_pred_lower, y_pred_upper,
                        alpha=0.3, color='blue', label='Prediction Interval')

        ax.set_xlabel('Time' if timestamps is not None else 'Sample')
        ax.set_ylabel('Energy Consumption (MW)')
        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Add coverage info
        coverage_info = self.calculate_coverage(y_true, y_pred_lower, y_pred_upper)
        coverage_text = (f"Coverage: {coverage_info['coverage']*100:.1f}%\n"
                        f"Avg Width: {coverage_info['interval_width_mean']:.2f}")

        ax.text(0.02, 0.98, coverage_text,
               transform=ax.transAxes,
               verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        plt.tight_layout()

        if save_name:
            save_path = self.output_dir / save_name
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to {save_path}")

        return fig

    def save_metrics(self, metrics: Dict[str, float], filename: str = "metrics.json"):
        """
        Save metrics to JSON file

        Args:
            metrics: Dictionary of metrics
            filename: Output filename
        """
        import json

        output_path = self.output_dir / filename

        # Convert numpy types to Python native types
        clean_metrics = {}
        for k, v in metrics.items():
            if isinstance(v, (np.integer, np.floating)):
                clean_metrics[k] = float(v)
            else:
                clean_metrics[k] = v

        with open(output_path, 'w') as f:
            json.dump(clean_metrics, f, indent=2)

        print(f"Metrics saved to {output_path}")


if __name__ == "__main__":
    # Example usage
    print("ModelEvaluator - Example Usage")

    # Generate sample data
    np.random.seed(42)
    n_samples = 1000

    y_true = np.sin(np.linspace(0, 10, n_samples)) * 100 + 200
    y_pred = y_true + np.random.normal(0, 10, n_samples)
    timestamps = pd.date_range('2024-01-01', periods=n_samples, freq='H')

    # Initialize evaluator
    evaluator = ModelEvaluator()

    # Calculate metrics
    metrics = evaluator.calculate_metrics(y_true, y_pred)
    print("\nMetrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v:.2f}")

    # Plot predictions
    evaluator.plot_predictions(y_true, y_pred, timestamps,
                              save_name="example_predictions.png")

    # Plot residuals
    evaluator.plot_residuals(y_true, y_pred, timestamps,
                            save_name="example_residuals.png")

    print("\nExample completed!")
