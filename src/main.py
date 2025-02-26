import base64
import io
import logging
import re
from openai.types.chat.chat_completion import ChatCompletion
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler

from app import App
from telegram.helpers import escape_markdown
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_assistant_message_param import (
    ChatCompletionAssistantMessageParam,
)

from auth import auth_required
from context import LLMContext

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=App.settings.logging_level,
)

PREFIX_REGEX = re.compile(
    App.settings.bot.group_chat_react_regex_prefix + ".+", re.IGNORECASE
)


def prepare_text(content: str) -> str:
    txt = (
        re.sub(App.settings.bot.group_chat_react_regex_prefix, "", content)
        .removeprefix(",")
        .removeprefix(".")
        .strip()
    )
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


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    chat_id = update.effective_chat.id

    async with App.auth_database.connect() as db:
        await db.add_chat(chat_id)

    await update.effective_chat.send_message("Authorized😎")


@auth_required(App.auth_database)
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert context.user_data is not None
    assert update.message is not None
    assert update.effective_user is not None
    assert update.effective_chat is not None

    if (
        update.message.reply_to_message
        and update.message.reply_to_message.from_user
        and update.message.reply_to_message.from_user.id != context.bot.id
    ):
        return

    llm_context = LLMContext.from_tg_context(context) or LLMContext(update)

    content = []

    if update.message.text:
        content.append({"type": "text", "text": prepare_text(update.message.text)})

    if update.message.photo:
        buff = io.BytesIO()
        photo = await update.message.photo[-1].get_file()
        await photo.download_to_memory(buff)
        base64_photo = base64.b64encode(buff.getvalue()).decode()
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64," + base64_photo,
                    "detail": "auto",
                },
            }
        )

    if not content:
        return

    user_context = ChatCompletionUserMessageParam(
        role="user",
        content=content,
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

    if err := getattr(response, "error", None):
        if err["code"] == 429:
            await update.message.reply_text(
                "Лимит запросов в минуту исчерпан, попробуйте позднее."
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


@auth_required(App.auth_database)
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
    CommandHandler(
        "start",
        register,
        filters.Regex(re.compile(f"^/start {App.settings.bot.password}")),
    ),
    CommandHandler("clear", clear_user_data),
    MessageHandler(
        (filters.Regex(PREFIX_REGEX) & filters.ChatType.GROUPS)
        | ((filters.TEXT | filters.PHOTO) & filters.ChatType.PRIVATE)
        | (filters.REPLY & filters.TEXT),
        echo,
    ),
]

if __name__ == "__main__":
    App.entrypoint(HANDLERS, error_handler=error_handler)
