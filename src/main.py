import html
import logging
from openai.types.chat.chat_completion import ChatCompletion
from telegram import Update
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    filters,
)

from app import App
from telegram.helpers import escape_markdown

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=App.settings.logging_level,
)


def prepare_content(content: str) -> str:
    txt = content.removeprefix(App.settings.bot.group_chat_react).strip()
    return escape_markdown(txt)


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


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert context.user_data is not None
    assert update.message is not None
    assert update.message.text is not None
    assert update.effective_user is not None
    assert update.effective_chat is not None

    user_model_context = context.user_data.get(
        "model_context",
        App.initialize_model_context(),
    )

    model_message = {"role": "user", "content": prepare_content(update.message.text)}
    user_model_context.append(model_message)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    response = await App.openai_client.chat.completions.create(
        model=App.settings.openai.model,
        messages=[*App.settings.default_model_context, *user_model_context],
    )

    response = prepare_response(response)

    if not response:
        await update.message.reply_text("Ошибка при обработке запроса.")
        return

    user_model_context.append({"role": "assistant", "content": response})

    await update.message.reply_text(response)

    context.user_data["model_context"] = user_model_context


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
    MessageHandler(
        filters.Regex(rf"^{App.settings.bot.group_chat_react} .+")
        & filters.ChatType.GROUPS,
        echo,
    ),
    MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, echo),
]

if __name__ == "__main__":
    App.entrypoint(HANDLERS, error_handler=error_handler)
