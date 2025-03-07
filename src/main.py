import base64
import io
import logging
import re
from openai.types.chat.chat_completion import ChatCompletion
from telegram import Message, PhotoSize, Sticker, Update
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


async def prepare_photo(photo: tuple[PhotoSize, ...] | Sticker) -> str:
    buff = io.BytesIO()

    if isinstance(photo, Sticker):
        thumbnail = photo.thumbnail
        file = await thumbnail.get_file() if thumbnail else await photo.get_file()
    else:
        file = await photo[-1].get_file()

    await file.download_to_memory(buff)
    return "data:image/jpeg;base64," + base64.b64encode(buff.getvalue()).decode()


async def resolve_message_to_content(message: Message) -> list[dict]:
    content = []

    if message.text:
        content.append(
            {
                "type": "text",
                "text": prepare_text(message.text),
            }
        )

    if message.photo:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": await prepare_photo(message.photo),
                    "detail": "auto",
                },
            }
        )

    if message.sticker and message.sticker.emoji:
        content.append(
            {
                "type": "text",
                "text": message.sticker.emoji,
            }
        )

    return content


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    chat_id = update.effective_chat.id

    async with App.auth_database.connect() as db:
        await db.add_chat(chat_id)

    await update.effective_chat.send_message("Authorized😎")


@auth_required(App.auth_database)
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    assert update.effective_user is not None
    assert update.effective_chat is not None

    llm_context = LLMContext.from_tg_context(context) or LLMContext()

    content = []

    if update.message.reply_to_message:
        reply = update.message.reply_to_message

        is_private_chat = update.effective_chat.type == ChatType.PRIVATE
        replied_directly = reply.from_user and reply.from_user.id == context.bot.id
        reply_contains_prefix = update.message.text and PREFIX_REGEX.search(
            update.message.text
        )

        if not replied_directly and not reply_contains_prefix and not is_private_chat:
            return

        content.extend(await resolve_message_to_content(reply))

    content.extend(await resolve_message_to_content(update.message))

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
        messages=llm_context.get_content(update),
    )

    if err := getattr(response, "error", None):
        if err["code"] == 429:
            await update.message.reply_text(
                "Лимит запросов в минуту исчерпан, попробуйте позднее."
            )
            return

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

    llm_context.save_to_chat_data(context)


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


ALLOWED_CONTENTS = filters.TEXT | filters.PHOTO | filters.Sticker.ALL

IS_GROUP_CHAT_MESSAGE = (
    filters.Regex(PREFIX_REGEX) & filters.ChatType.GROUPS & ALLOWED_CONTENTS
)
IS_GROUP_CHAT_REPLY = filters.REPLY & filters.ChatType.GROUPS & ALLOWED_CONTENTS
IS_PRIVATE_CHAT_MESSAGE = filters.ChatType.PRIVATE & ALLOWED_CONTENTS

HANDLERS = [
    CommandHandler(
        "start",
        register,
        filters.Regex(re.compile(f"^/start {App.settings.bot.password}")),
    ),
    CommandHandler("clear", clear_user_data),
    MessageHandler(
        IS_GROUP_CHAT_MESSAGE | IS_GROUP_CHAT_REPLY | IS_PRIVATE_CHAT_MESSAGE,
        echo,
    ),
]

if __name__ == "__main__":
    App.entrypoint(HANDLERS, error_handler=error_handler)
