from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database & Connection Pooler
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: str

    # Caching & Locking
    REDIS_URL: str

    # Event Streaming
    KAFKA_BOOTSTRAP_SERVERS: str

    # Message Queue
    RABBITMQ_DEFAULT_USER: str
    RABBITMQ_DEFAULT_PASS: str
    RABBITMQ_HOST: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Instantiate centralized settings
settings = Settings()
