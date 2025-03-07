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
    def __init__(self) -> None:
        self._deque = deque([], maxlen=App.settings.openai.context_length)
        self._updated_at = datetime.now()
        self.dialogue_members = []

    def prepare_prompt(self, update: Update) -> str:
        prompt = App.settings.default_model_prompt

        if App.settings.bot.name:
            prompt += f"\nYour name is: {App.settings.bot.name}\n"

        username = update.effective_user and update.effective_user.username
        name = update.effective_user and update.effective_user.first_name

        if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
            prompt += "You are messaging with user in private telegram chat now."

            if username:
                prompt += f"\nUser telegram nickname is: {username}."

            if name:
                prompt += f"\nUser name is: {name}."

        if update.effective_chat and update.effective_chat.type in (
            ChatType.GROUP,
            ChatType.SUPERGROUP,
        ):
            prompt += "You are member of group chat now."

            if username:
                prompt += f"\nThe last message was from user nicknamed as: {username}."

            if name:
                prompt += f"\nThe last message was from user named as: {name}."

            prompt += f"\nYou are member of group chat with name: {update.effective_chat.title}"

            member = (username, name)

            if member not in self.dialogue_members:
                self.dialogue_members.append(member)

            members_fmt = [
                (f"username: {username}" if username else "")
                + (f"name: {name}" if name else "")
                for username, name in self.dialogue_members
                if username or name
            ]

            if members_fmt:
                prompt += f"\nMembers of this dialogue are: {'; '.join(members_fmt)}. Here only those who has username or name."

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

    def get_content(self, update: Update) -> list:
        system_prompt = self.prepare_prompt(update)
        sys_msg = ChatCompletionSystemMessageParam(role="system", content=system_prompt)
        return [sys_msg, *self._deque]

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
