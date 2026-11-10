from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Diagramador UML"
    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174"

    # IA (Google Gemini, SDK `google-genai`): comandos de texto/voz (CU11),
    # reconocimiento por foto (CU12) y el agente Senior del chat grupal.
    # Opcional al arrancar (no rompe `pytest`); `app/services/ai/gemini_client.py`
    # valida que esté presente recién al llamar a la API, con un error claro.
    # La key vive solo en el backend: el frontend nunca habla con Gemini.
    GEMINI_API_KEY: str | None = None
    # Modelo principal: texto + tool calling (comandos, agente Senior).
    GEMINI_MODEL: str = "gemini-3.5-flash"
    # Modelo para importar diagramas desde imagen (puede ser el mismo).
    GEMINI_VISION_MODEL: str = "gemini-3.5-flash"
    # Respaldo si el principal responde 429/503 después de los reintentos.
    GEMINI_FALLBACK_MODEL: str | None = "gemini-3.1-flash-lite"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origen.strip() for origen in self.CORS_ORIGINS.split(",") if origen.strip()]


settings = Settings()
