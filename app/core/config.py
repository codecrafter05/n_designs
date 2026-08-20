from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import quote_plus


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ALGORITHM: str = "HS256"
    WHATSAPP_NUMBER: str = "97300000000"

    MAIL_HOST: str = ""
    MAIL_PORT: int = 465
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_ENCRYPTION: str = "ssl"
    MAIL_FROM_ADDRESS: str = ""
    MAIL_FROM_NAME: str = "N Designs"
    ADMIN_NOTIFICATION_EMAIL: str = ""
    SITE_URL: str = "http://127.0.0.1:8000"
    TAP_SECRET_KEY: str = ""
    TAP_PUBLIC_KEY: str = ""

    @model_validator(mode="after")
    def default_admin_notification_email(self):
        if not (self.ADMIN_NOTIFICATION_EMAIL or "").strip():
            self.ADMIN_NOTIFICATION_EMAIL = (self.MAIL_FROM_ADDRESS or "").strip()
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def DATABASE_URL(self) -> str:
        password = quote_plus(self.DB_PASSWORD)
        return (
            f"mysql+pymysql://{self.DB_USER}:{password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
