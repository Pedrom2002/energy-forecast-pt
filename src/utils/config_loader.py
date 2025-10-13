"""
Utility for loading configurations
"""

import yaml
from pathlib import Path
from typing import Dict, Any
from loguru import logger


class ConfigLoader:
    """Project configuration loader"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)

        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load YAML configuration file"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        logger.info(f"Loaded configuration from {self.config_path}")
        return config

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation

        Args:
            key_path: key path (e.g., "models.xgboost.params.learning_rate")
            default: default value if key doesn't exist

        Returns:
            Configuration value or default
        """
        keys = key_path.split('.')
        value = self.config

        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def __getitem__(self, key: str) -> Any:
        """Allows direct access as dict"""
        return self.config[key]


if __name__ == "__main__":
    config = ConfigLoader()
    print(config.get('models.xgboost.params.learning_rate'))
