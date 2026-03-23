"""Configuration loader module (class-based interface).

Wraps the functional API from config.py in a class for convenience.
Provides dot-notation access, runtime reload, and Mapping-style helpers.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Known top-level keys defined by the project's config schema.
# Any key not in this set triggers a warning so typos are caught early.
_KNOWN_KEYS: frozenset[str] = frozenset(
    {
        "models",
        "features",
        "api",
        "training",
        "data",
        "logging",
    }
)
# Keys that must be present for core functionality.
_REQUIRED_KEYS: frozenset[str] = frozenset({"models"})


class ConfigLoader:
    """Project configuration loader with dot-notation access and hot-reload.

    Example::

        cfg = ConfigLoader("config/config.yaml")
        lr = cfg.get("models.xgboost.params.learning_rate", default=0.1)
        cfg.reload()  # Pick up changes without restarting
    """

    def __init__(self, config_path: str = "config/config.yaml") -> None:
        """Initialise the loader from a YAML file.

        Args:
            config_path: Path to the YAML configuration file.  If the file
                does not exist an empty configuration is used and a warning
                is logged.
        """
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            logger.warning(
                "Config file not found: %s -- using empty configuration. "
                "Create the file to provide custom settings.",
                config_path,
            )
            self.config: dict[str, Any] = {}
        else:
            self.config = self._load()

    def _load(self) -> dict[str, Any]:
        """Read and parse the YAML config file.

        Returns:
            Parsed configuration dictionary.
        """
        with open(self.config_path, encoding="utf-8") as f:
            config: dict[str, Any] = yaml.safe_load(f) or {}
        logger.info("Loaded configuration from %s", self.config_path)
        self._validate_schema(config)
        return config

    def _validate_schema(self, config: dict[str, Any]) -> None:
        """Warn on unknown or missing top-level configuration keys.

        Args:
            config: The parsed configuration dictionary to validate.
        """
        unknown = set(config.keys()) - _KNOWN_KEYS
        if unknown:
            logger.warning(
                "Unknown configuration key(s): %s -- check for typos in %s",
                sorted(unknown),
                self.config_path,
            )
        for required in _REQUIRED_KEYS:
            if required not in config:
                logger.warning(
                    "Required configuration key '%s' is missing from %s",
                    required,
                    self.config_path,
                )

    def reload(self) -> None:
        """Reload configuration from disk, replacing the current in-memory state."""
        if not self.config_path.exists():
            logger.warning(
                "Config file not found during reload: %s -- keeping current configuration.",
                self.config_path,
            )
            return
        self.config = self._load()
        logger.info("Reloaded configuration from %s", self.config_path)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get a configuration value using dot-separated key notation.

        Args:
            key_path: Dot-separated path
                (e.g. ``"models.xgboost.params.learning_rate"``).
            default: Value to return when the key is absent.

        Returns:
            The value at *key_path*, or *default* if any key in the path
            is missing.
        """
        keys = key_path.split(".")
        value: Any = self.config
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def keys(self) -> list[str]:
        """Return the top-level configuration keys.

        Returns:
            List of top-level key strings.
        """
        return list(self.config.keys())

    def values(self) -> list[Any]:
        """Return the top-level configuration values.

        Returns:
            List of top-level values.
        """
        return list(self.config.values())

    def items(self) -> list[tuple[str, Any]]:
        """Return the top-level (key, value) pairs.

        Returns:
            List of ``(key, value)`` tuples.
        """
        return list(self.config.items())

    def __getitem__(self, key: str) -> Any:
        """Access a top-level configuration key.

        Args:
            key: Top-level configuration key.

        Returns:
            The value associated with *key*.

        Raises:
            KeyError: If *key* is not present.
        """
        return self.config[key]

    def __contains__(self, key: str) -> bool:
        """Check if a top-level key is present.

        Args:
            key: Top-level configuration key.

        Returns:
            True if *key* exists.
        """
        return key in self.config

    def __iter__(self) -> Iterator[str]:
        """Iterate over top-level configuration keys.

        Returns:
            Iterator of key strings.
        """
        return iter(self.config)

    def __repr__(self) -> str:
        """Return a developer-friendly representation.

        Returns:
            String showing path and top-level keys.
        """
        return f"ConfigLoader(path={self.config_path!r}, keys={self.keys()!r})"
