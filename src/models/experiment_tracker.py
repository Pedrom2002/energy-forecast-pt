"""Lightweight file-based experiment tracker.

Records every training run with its configuration, metrics, data hashes, and
environment info.  All experiments are saved as individual JSON files under
``experiments/`` and indexed in ``experiments/index.json``.

This is a zero-dependency alternative to MLflow/W&B that provides the
essential tracking needed for reproducibility without requiring a server.

Usage::

    from src.models.experiment_tracker import ExperimentTracker

    tracker = ExperimentTracker()
    run_id = tracker.start_run(
        experiment_name="with_lags_v5",
        model_key="catboost",
        hyperparams={"iterations": 500, "depth": 10},
    )
    tracker.log_metrics(run_id, {"rmse": 82.27, "mape": 4.48})
    tracker.log_artifact(run_id, "model_path", "data/models/checkpoints/best_model.pkl")
    tracker.end_run(run_id, status="completed")
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_EXPERIMENTS_DIR = Path("experiments")


class ExperimentTracker:
    """File-based experiment tracker for ML training runs.

    Each run is stored as a JSON file: ``experiments/<run_id>.json``.
    An index file (``experiments/index.json``) provides a summary of all runs
    for quick lookup and comparison.

    Args:
        base_dir: Directory where experiment files are stored.
    """

    def __init__(self, base_dir: Path | str = DEFAULT_EXPERIMENTS_DIR) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.base_dir / "index.json"

    def start_run(
        self,
        experiment_name: str,
        model_key: str,
        hyperparams: dict[str, Any] | None = None,
        feature_names: list[str] | None = None,
        data_hash: str | None = None,
        tags: dict[str, str] | None = None,
        reproducibility_info: dict[str, Any] | None = None,
    ) -> str:
        """Start a new experiment run.

        Args:
            experiment_name: Human-readable name for this experiment.
            model_key: Model type identifier (e.g., "catboost").
            hyperparams: Model hyperparameters used for this run.
            feature_names: List of feature column names.
            data_hash: SHA-256 hash of the training data for versioning.
            tags: Free-form key-value metadata.
            reproducibility_info: Environment snapshot from
                :func:`~src.utils.reproducibility.get_reproducibility_info`.

        Returns:
            Unique run ID string.
        """
        run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]

        run_data: dict[str, Any] = {
            "run_id": run_id,
            "experiment_name": experiment_name,
            "model_key": model_key,
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": None,
            "hyperparams": hyperparams or {},
            "feature_names": feature_names,
            "n_features": len(feature_names) if feature_names else None,
            "data_hash": data_hash,
            "tags": tags or {},
            "metrics": {},
            "cv_results": None,
            "baseline_comparison": None,
            "feature_selection_report": None,
            "artifacts": {},
            "reproducibility": reproducibility_info,
        }

        self._save_run(run_id, run_data)
        logger.info("Experiment started: %s (run_id=%s)", experiment_name, run_id)
        return run_id

    def log_metrics(self, run_id: str, metrics: dict[str, float], prefix: str = "") -> None:
        """Log metrics for a run.

        Args:
            run_id: The run to update.
            metrics: Dictionary of metric name-value pairs.
            prefix: Optional prefix for metric names (e.g., "test_").
        """
        run_data = self._load_run(run_id)
        for key, value in metrics.items():
            name = f"{prefix}{key}" if prefix else key
            run_data["metrics"][name] = float(value) if not isinstance(value, str) else value
        self._save_run(run_id, run_data)

    def log_cv_results(
        self,
        run_id: str,
        cv_scores: dict[str, list[float]],
        best_key: str,
    ) -> None:
        """Log cross-validation results.

        Args:
            run_id: The run to update.
            cv_scores: Per-model CV scores (model_key → list of RMSE per fold).
            best_key: Key of the best model selected by CV.
        """
        run_data = self._load_run(run_id)

        cv_summary = {}
        for key, scores in cv_scores.items():
            import numpy as np

            cv_summary[key] = {
                "scores": [float(s) for s in scores],
                "mean": float(np.mean(scores)),
                "std": float(np.std(scores)),
            }

        run_data["cv_results"] = {
            "model_scores": cv_summary,
            "best_model_key": best_key,
            "n_folds": len(next(iter(cv_scores.values()))) if cv_scores else 0,
        }
        self._save_run(run_id, run_data)

    def log_baseline_comparison(
        self,
        run_id: str,
        baseline_results: dict[str, dict[str, float]],
        model_metrics: dict[str, float],
    ) -> None:
        """Log baseline comparison results.

        Args:
            run_id: The run to update.
            baseline_results: Results from
                :func:`~src.models.baselines.evaluate_all_baselines`.
            model_metrics: The ML model's metrics for comparison.
        """
        run_data = self._load_run(run_id)

        comparison = {
            "baselines": {},
            "model": {k: float(v) for k, v in model_metrics.items() if isinstance(v, (int, float))},
            "improvement_over_best_baseline": {},
        }

        best_baseline_rmse = float("inf")
        best_baseline_name = ""

        for name, metrics in baseline_results.items():
            clean = {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))}
            comparison["baselines"][name] = clean
            if clean.get("rmse", float("inf")) < best_baseline_rmse:
                best_baseline_rmse = clean["rmse"]
                best_baseline_name = name

        model_rmse = model_metrics.get("rmse", 0)
        if best_baseline_rmse > 0 and model_rmse > 0:
            comparison["improvement_over_best_baseline"] = {
                "best_baseline": best_baseline_name,
                "baseline_rmse": best_baseline_rmse,
                "model_rmse": float(model_rmse),
                "rmse_reduction_pct": round((1 - model_rmse / best_baseline_rmse) * 100, 2),
            }

        run_data["baseline_comparison"] = comparison
        self._save_run(run_id, run_data)

    def log_feature_selection(
        self,
        run_id: str,
        report: dict[str, Any],
    ) -> None:
        """Log feature selection report.

        Args:
            run_id: The run to update.
            report: Report from :func:`~src.models.feature_selection.select_features`.
        """
        run_data = self._load_run(run_id)
        # Convert numpy types to native Python
        clean_report = json.loads(json.dumps(report, default=str))
        run_data["feature_selection_report"] = clean_report
        self._save_run(run_id, run_data)

    def log_artifact(self, run_id: str, name: str, path: str) -> None:
        """Log an artifact path for a run.

        Args:
            run_id: The run to update.
            name: Artifact name (e.g., "model_checkpoint").
            path: File path to the artifact.
        """
        run_data = self._load_run(run_id)
        run_data["artifacts"][name] = str(path)
        self._save_run(run_id, run_data)

    def end_run(self, run_id: str, status: str = "completed") -> None:
        """Mark a run as completed (or failed).

        Args:
            run_id: The run to finalise.
            status: Final status ("completed", "failed", "interrupted").
        """
        run_data = self._load_run(run_id)
        run_data["status"] = status
        run_data["ended_at"] = datetime.now(UTC).isoformat()
        self._save_run(run_id, run_data)
        self._update_index(run_data)
        logger.info("Experiment %s: %s (run_id=%s)", status, run_data["experiment_name"], run_id)

    def list_runs(
        self,
        experiment_name: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List experiment runs, optionally filtered.

        Args:
            experiment_name: Filter by experiment name.
            status: Filter by status.

        Returns:
            List of run summary dicts.
        """
        index = self._load_index()
        runs = index.get("runs", [])
        if experiment_name:
            runs = [r for r in runs if r.get("experiment_name") == experiment_name]
        if status:
            runs = [r for r in runs if r.get("status") == status]
        return runs

    def get_best_run(
        self,
        experiment_name: str | None = None,
        metric: str = "test_rmse",
        lower_is_better: bool = True,
    ) -> dict[str, Any] | None:
        """Find the best run by a given metric.

        Args:
            experiment_name: Filter by experiment name.
            metric: Metric to compare.
            lower_is_better: Whether lower values are better.

        Returns:
            The best run data, or None if no matching runs exist.
        """
        runs = self.list_runs(experiment_name=experiment_name, status="completed")
        if not runs:
            return None

        # Load full run data for metric comparison
        best_run = None
        best_value = float("inf") if lower_is_better else float("-inf")

        for summary in runs:
            run_data = self._load_run(summary["run_id"])
            value = run_data.get("metrics", {}).get(metric)
            if value is None:
                continue
            if lower_is_better and value < best_value or not lower_is_better and value > best_value:
                best_value = value
                best_run = run_data

        return best_run

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _run_path(self, run_id: str) -> Path:
        return self.base_dir / f"{run_id}.json"

    def _save_run(self, run_id: str, data: dict[str, Any]) -> None:
        with open(self._run_path(run_id), "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _load_run(self, run_id: str) -> dict[str, Any]:
        path = self._run_path(run_id)
        if not path.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")
        with open(path) as f:
            return json.load(f)

    def _load_index(self) -> dict[str, Any]:
        if not self._index_path.exists():
            return {"runs": []}
        with open(self._index_path) as f:
            return json.load(f)

    def _update_index(self, run_data: dict[str, Any]) -> None:
        index = self._load_index()

        summary = {
            "run_id": run_data["run_id"],
            "experiment_name": run_data["experiment_name"],
            "model_key": run_data["model_key"],
            "status": run_data["status"],
            "started_at": run_data["started_at"],
            "ended_at": run_data["ended_at"],
            "metrics_summary": {
                k: v
                for k, v in run_data.get("metrics", {}).items()
                if k in ("test_rmse", "test_mae", "test_mape", "test_r2")
            },
        }

        # Replace existing entry if same run_id
        index["runs"] = [r for r in index.get("runs", []) if r["run_id"] != run_data["run_id"]]
        index["runs"].append(summary)

        # Sort by start time (newest first)
        index["runs"].sort(key=lambda r: r.get("started_at", ""), reverse=True)

        with open(self._index_path, "w") as f:
            json.dump(index, f, indent=2)
