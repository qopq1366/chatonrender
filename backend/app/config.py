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
    telegram_bot_username: str = os.getenv("TELEGRAM_BOT_USERNAME", "@change-me-bot")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    login_code_ttl_minutes: int = int(os.getenv("LOGIN_CODE_TTL_MINUTES", "5"))
    tg_link_code_ttl_minutes: int = int(os.getenv("TG_LINK_CODE_TTL_MINUTES", "5"))


settings = Settings()

