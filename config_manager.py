"""Configuration manager for Predictipulse."""

import json
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    "kelly_multiplier": 0.5,
    "target_buy_ev": 0.05,
    "target_sell_ev": 0.05,
    "max_percentage_bet": 10,
    "max_dollar_bet": 50,
    "min_true_prob": 0.15,
    "max_true_prob": 0.85,
    "sports": ["NBA", "NFL", "NHL"],
    "trading_start": 0,
    "trading_end": 24,
    "boltodds_api_key": "",  # Add your BoltOdds API key here
}


class ConfigManager:
    """Manages loading and saving Predictipulse configuration."""

    def __init__(self, path: str = "config.json"):
        self.path = Path(path)

    def load(self) -> Dict[str, Any]:
        """Load config from file, creating with defaults if not exists."""
        if not self.path.exists():
            self.save(DEFAULT_CONFIG)
            return dict(DEFAULT_CONFIG)
        with self.path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge defaults for any missing keys
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        return merged

    def save(self, config: Dict[str, Any]) -> None:
        """Save config to file."""
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def reset(self) -> Dict[str, Any]:
        """Reset config to defaults."""
        self.save(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
