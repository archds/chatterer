from pathlib import Path
from typing import Literal
from openai import BaseModel
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CONTEXT = """
You are a helpful assistant with integration as telegram bot.
Preferred language: Russian.
Response in telegram text formatting rules.
Response less than 4096 symbols.
Do not send greetings every time.
"""


class BotSettings(BaseModel):
    token: str | None = None
    secret_token: str | None = None
    port: int = 8443
    listen: str = "0.0.0.0"
    key_path: Path | None = None
    cert_path: Path | None = None
    domain: str
    persistence_path: Path
    mode: Literal["webhook", "polling"]
    group_chat_react_regex_prefix: str
    password: str

    def get_webhook_url(self):
        return f"https://{self.domain}:{self.port}"


class OpenaiSDKSettings(BaseModel):
    base_url: str
    token: str
    model: str
    context_length: int = Field(default=5)
    context_timeout: int = Field(default=600)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    logging_level: str = Field(default="INFO", validation_alias="LOGGING_LEVEL")

    openai: OpenaiSDKSettings
    bot: BotSettings

    default_model_prompt: str = DEFAULT_CONTEXT
