from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Diagramador UML"
    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174"

    # CU11 — interpretación de comandos de voz vía function calling. Opcional
    # (no requerida al arrancar) para no romper `pytest`/entornos sin la key
    # configurada todavía -- `app/services/comandos_voz.py` valida que esté
    # presente recién al momento de llamar a la API, con un error claro.
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    # CU12 — modelo aparte solo para el reconocimiento de diagramas por foto.
    # Medido con una imagen real: gpt-4o-mini perdía clases e inventaba
    # relaciones distintas en cada intento; gpt-4o, estable (ver encabezado
    # de `app/services/reconocimiento_foto.py`). Comandos de voz y el agente
    # siguen con sus propios modelos (texto, no visión).
    OPENAI_VISION_MODEL: str = "gpt-4o"
    # CU11 — modelo aparte para los comandos de voz: un solo comando puede
    # crear varias clases y deducir tipo/multiplicidad de sus relaciones por
    # el dominio, algo en lo que gpt-4o-mini se equivoca bastante más. El
    # agente (CU13) sigue con OPENAI_MODEL.
    OPENAI_VOZ_MODEL: str = "gpt-4o"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origen.strip() for origen in self.CORS_ORIGINS.split(",") if origen.strip()]


settings = Settings()
