import os


class Settings:
    app_name: str = os.getenv("APP_NAME", "ChatOnRender API")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./chat.db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-production")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 30))
    )
    integration_api_key: str = os.getenv("INTEGRATION_API_KEY", "change-me-in-production")


settings = Settings()

