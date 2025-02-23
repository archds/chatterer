from datetime import datetime, timedelta
import html
import logging
from openai.types.chat.chat_completion import ChatCompletion
from telegram import ChatMember, MessageEntity, Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler

from app import App
from telegram.helpers import escape_markdown
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_assistant_message_param import (
    ChatCompletionAssistantMessageParam,
)

from context import LLMContext

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=App.settings.logging_level,
)


def prepare_content(content: str) -> str:
    txt = content.removeprefix(App.settings.bot.group_chat_react).strip()
    return txt


def prepare_response(response: ChatCompletion) -> str | None:
    try:
        first_choice = response.choices[0]
    except IndexError:
        return

    if not first_choice.message:
        return

    if not first_choice.message.content:
        return

    text = first_choice.message.content.replace("*  ", "-  ")

    return text


def prepare_prompt(update: Update) -> str:
    prompt = App.settings.default_model_prompt

    if username := update.effective_user and update.effective_user.username:
        prompt += f"\nYou are messaging with user nicknamed as: {username}"

    if name := update.effective_user and update.effective_user.first_name:
        prompt += f"\nYou are messaging with user named as: {name}"

    if update.effective_chat and update.effective_chat.type == ChatType.GROUP:
        prompt += (
            f"\nYou are member of group chat with name: {update.effective_chat.title}"
        )

    return prompt


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert context.user_data is not None
    assert update.message is not None
    assert update.message.text is not None
    assert update.effective_user is not None
    assert update.effective_chat is not None

    if (
        update.message.reply_to_message
        and update.message.reply_to_message.from_user
        and update.message.reply_to_message.from_user.id != context.bot.id
    ):
        return

    llm_context = LLMContext.from_tg_context(context) or LLMContext(update)

    user_context = ChatCompletionUserMessageParam(
        role="user",
        content=prepare_content(update.message.text),
        name=update.effective_user.first_name,
    )
    llm_context.add_context(user_context)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    response = await App.openai_client.chat.completions.create(
        model=App.settings.openai.model,
        messages=llm_context.content,
    )

    response = prepare_response(response)

    if not response:
        await update.message.reply_text("Ошибка при обработке запроса.")
        return

    assistant_context = ChatCompletionAssistantMessageParam(
        role="assistant", content=response
    )
    llm_context.add_context(assistant_context)

    try:
        await update.message.reply_text(response)
    except Exception:
        await update.message.reply_text(escape_markdown(response))

    context.user_data["llm_context"] = llm_context


async def clear_user_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_message

    if context.user_data is not None:
        context.user_data.clear()

    await update.effective_message.reply_text("Контекст диалога очищен.")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.error:
        logging.exception(context.error)

    if update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Ошибка при обработке запроса.",
        )
        return


HANDLERS = [
    CommandHandler("clear", clear_user_data),
    MessageHandler(
        (
            filters.Regex(rf"^{App.settings.bot.group_chat_react} .+")
            & filters.ChatType.GROUPS
        )
        | (filters.TEXT & filters.ChatType.PRIVATE)
        | (filters.REPLY & filters.TEXT),
        echo,
    ),
]

if __name__ == "__main__":
    App.entrypoint(HANDLERS, error_handler=error_handler)
