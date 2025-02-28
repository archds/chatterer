from collections import deque
from typing import Callable, Sequence
import httpx
import openai
from telegram.ext import Application
from telegram.ext import (
    ApplicationBuilder,
    Defaults,
    AIORateLimiter,
    BaseHandler,
)

from conf import Settings
from auth import AuthorizedChatsDatabase


class App:
    settings = Settings()  # type: ignore

    http_client: httpx.AsyncClient = httpx.AsyncClient(http2=True, http1=True)
    bot_application_builder: ApplicationBuilder = (
        ApplicationBuilder()
        .defaults(defaults=Defaults(parse_mode="Markdown"))
        .http_version("2.0")
        .rate_limiter(AIORateLimiter())
    )
    openai_client = openai.AsyncOpenAI(
        base_url=settings.openai.base_url,
        api_key=settings.openai.token,
        http_client=http_client,
    )
    auth_database = AuthorizedChatsDatabase(
        settings.bot.persistence_path / "auth.sqlite"
    )

    bot_application: Application

    @classmethod
    def initialize_llm_context(cls) -> deque:
        return deque([], maxlen=cls.settings.openai.context_length)

    @classmethod
    def entrypoint(cls, handlers: Sequence[BaseHandler], *, error_handler: Callable):
        if cls.settings.bot.token:
            cls.bot_application_builder.token(cls.settings.bot.token)

        cls.bot_application = cls.bot_application_builder.build()
        cls.bot_application.add_handlers(handlers)
        cls.bot_application.add_error_handler(error_handler)

        if cls.settings.bot.mode == "webhook":
            if not cls.settings.bot.secret_token:
                raise ValueError("Secret token is required for webhook mode")

            if not cls.settings.bot.domain:
                raise ValueError("Domain is required for webhook mode")

            cls.bot_application.run_webhook(
                listen=cls.settings.bot.listen,
                port=cls.settings.bot.port,
                secret_token=cls.settings.bot.secret_token,
                key=cls.settings.bot.key_path,
                cert=cls.settings.bot.cert_path,
                webhook_url=cls.settings.bot.get_webhook_url(),
                allowed_updates=("message",),
            )

        if cls.settings.bot.mode == "polling":
            if not cls.settings.bot.token:
                raise ValueError("Token is required for polling mode")

            cls.bot_application.run_polling()
