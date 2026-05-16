from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gemini_api_key: str = ""
    dart_api_key: str = ""
    app_env: str = "development"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@dataclass
class FeatureModelConfig:
    provider: str
    model: str
    max_tokens: int


_model_config: dict | None = None


def _load_model_config() -> dict:
    global _model_config
    if _model_config is None:
        config_path = Path(__file__).parent / "model_config.yaml"
        with open(config_path) as f:
            _model_config = yaml.safe_load(f)
    return _model_config


def get_feature_config(feature: str) -> FeatureModelConfig:
    config = _load_model_config()
    feat = config.get("features", {}).get(feature, config.get("defaults", {}))
    return FeatureModelConfig(
        provider=feat["provider"],
        model=feat["model"],
        max_tokens=feat.get("max_tokens", 2048),
    )
