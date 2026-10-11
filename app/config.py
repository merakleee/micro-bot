from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    member_token: str = ""
    admin_api_key: str = ""
    database_path: str = "data/registry.sqlite3"
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemma-4-31b-it:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
