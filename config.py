"""Application configuration loaded from .env file or Streamlit secrets."""
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


def _inject_streamlit_secrets() -> None:
    """Copy Streamlit secrets into environment variables (Streamlit Cloud support)."""
    try:
        import streamlit as st
        secrets = st.secrets

        for key, value in secrets.items():
            if isinstance(value, str):
                # Force override (setdefault ignores existing keys, causing the bug)
                os.environ[key.upper()] = value
            elif hasattr(value, "items"):
                # Handle nested TOML sections, e.g. [groq] / api_key = "..."
                for k, v in value.items():
                    if isinstance(v, str):
                        os.environ[k.upper()] = v
    except Exception:
        pass


_inject_streamlit_secrets()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite:///./learn_ai.db"

    # Groq (required for content generation)
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.1-8b-instant"

    # Notion (optional — only needed for notion_tool)
    notion_api_key: Optional[str] = None
    notion_root_page_id: Optional[str] = None

    # Application
    app_env: str = "development"
    log_level: str = "INFO"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()