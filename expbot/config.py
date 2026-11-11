from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    database_path: str = "expenses.db"
    timezone: str = "Asia/Bishkek"
    google_sheet_id: str = ""
    google_credentials_file: str = "credentials.json"
