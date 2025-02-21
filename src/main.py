import html
import logging
from openai.types.chat.chat_completion import ChatCompletion
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler

from app import App
from telegram.helpers import escape_markdown
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam
)

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

    assistant_context = context.user_data.get(
        "model_context",
        App.initialize_model_context(),
    )
    
    user_context = ChatCompletionUserMessageParam(
        role="user",
        content=prepare_content(update.message.text),
        name=update.effective_user.first_name,
    )

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    system_context = ChatCompletionSystemMessageParam(
        role="system",
        content=prepare_prompt(update),
    )

    response = await App.openai_client.chat.completions.create(
        model=App.settings.openai.model,
        messages=[system_context, *assistant_context, user_context],
    )

    response = prepare_response(response)

    if not response:
        await update.message.reply_text("Ошибка при обработке запроса.")
        return

    assistant_context.append({"role": "assistant", "content": response})

    await update.message.reply_text(response)

    context.user_data["model_context"] = assistant_context


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
