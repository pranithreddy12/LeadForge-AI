from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "LeadForge AI"
    app_debug: bool = False
    app_secret_key: str = "change-me"
    app_public_url: str = "http://localhost:3001"
    api_public_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3001"

    # DB
    database_url: str = Field(
        default="postgresql+psycopg://leadforge:leadforge@postgres:5432/leadforge"
    )

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Clerk
    clerk_secret_key: str = ""
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_webhook_secret: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_growth: str = ""
    stripe_price_scale: str = ""

    # OpenAI
    openai_api_key: str = ""
    openai_model_reasoning: str = "gpt-4o"
    openai_model_fast: str = "gpt-4o-mini"
    openai_model_embedding: str = "text-embedding-3-large"
    openai_embedding_dim: int = 1536  # truncated via OpenAI dimensions param; fits HNSW

    # Search providers
    tavily_api_key: str = ""
    serper_api_key: str = ""

    # Email validation
    hunter_api_key: str = ""
    neverbounce_api_key: str = ""

    # Storage
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket: str = "leadforge-uploads"

    # Observability
    sentry_dsn: str | None = None
    log_level: str = "INFO"

    # Feature flags
    feature_playwright_scrape: bool = True
    feature_ai_chat: bool = True
    feature_workflows: bool = True

    @field_validator("cors_origins")
    @classmethod
    def _split_csv(cls, v: str) -> str:
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
