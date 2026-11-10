from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/a_method_hiring"

    # AI is off by default; the app must be fully usable without it.
    AI_ENABLED: bool = False
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"


settings = Settings()

# Default safeguarding checklist created when an application enters the
# references stage. Plain constant, not an env-configurable setting.
DEFAULT_SAFEGUARDING_CHECKS = [
    "Identity verification",
    "Criminal record / police check",
    "Previous employer verification",
    "Safeguarding declaration signed",
]
