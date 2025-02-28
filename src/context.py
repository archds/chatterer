from collections import deque
from datetime import datetime, timedelta
from typing import Self
from telegram.constants import ChatType
from telegram import Update
from telegram.ext import ContextTypes
from app import App
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_assistant_message_param import (
    ChatCompletionAssistantMessageParam,
)


class LLMContext:
    def __init__(self, update: Update) -> None:
        self._deque = deque([], maxlen=App.settings.openai.context_length)
        self._updated_at = datetime.now()
        self._system_prompt = ChatCompletionSystemMessageParam(
            role="system",
            content=self.prepare_prompt(update),
        )

    def prepare_prompt(self, update: Update) -> str:
        prompt = App.settings.default_model_prompt

        if username := update.effective_user and update.effective_user.username:
            prompt += f"\nYou are messaging with user nicknamed as: {username}"

        if name := update.effective_user and update.effective_user.first_name:
            prompt += f"\nYou are messaging with user named as: {name}"

        if update.effective_chat and update.effective_chat.type == ChatType.GROUP:
            prompt += f"\nYou are member of group chat with name: {update.effective_chat.title}"

        return prompt

    def add_context(
        self,
        context: ChatCompletionUserMessageParam | ChatCompletionAssistantMessageParam,
    ) -> None:
        self._deque.append(context)
        self._updated_at = datetime.now()

    def save_to_chat_data(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_data = {
            "llm_context": self,
            "llm_context_updated_at": self._updated_at,
        }
        
        if context.chat_data is not None:
            context.chat_data.update(chat_data)

    @property
    def content(self) -> list:
        return [self._system_prompt, *self._deque]

    @classmethod
    def from_tg_context(cls, context: ContextTypes.DEFAULT_TYPE) -> Self | None:
        if not context.chat_data:
            return

        llm_context = context.chat_data.get("llm_context")

        if not llm_context:
            return

        llm_context_updated_at = context.chat_data.get("llm_context_updated_at")

        if llm_context_updated_at and (
            datetime.now() - llm_context_updated_at
            >= timedelta(seconds=App.settings.openai.context_timeout)
        ):
            return

        return llm_context
