from pathlib import Path
import aiosqlite
from datetime import datetime
from contextlib import asynccontextmanager
from typing import TypedDict
from functools import wraps
from telegram import Update
from telegram.ext import CallbackContext
from typing import Callable, Awaitable, Any


class ChatRecord(TypedDict):
    chat_id: int
    authorized_at: str


class AuthorizedChatsDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def connect(self):
        self.connection = await aiosqlite.connect(self.db_path)
        self.connection.row_factory = aiosqlite.Row
        try:
            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id INTEGER PRIMARY KEY,
                    authorized_at TIMESTAMP NOT NULL
                )
            """)
            await self.connection.commit()
            yield self
        finally:
            await self.connection.close()

    async def is_chat_authorized(self, chat_id: int) -> bool:
        cursor = await self.connection.execute(
            "SELECT chat_id FROM chats WHERE chat_id = ?", (chat_id,)
        )
        row = await cursor.fetchone()
        return row is not None

    async def add_chat(self, chat_id: int):
        authorized_at = datetime.now().isoformat()
        await self.connection.execute(
            """
            INSERT INTO chats (chat_id, authorized_at) VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET authorized_at = ?
        """,
            (chat_id, authorized_at, authorized_at),
        )
        await self.connection.commit()

    async def remove_chat(self, chat_id: int):
        await self.connection.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        await self.connection.commit()

    async def get_all_chats(self) -> list[ChatRecord]:
        cursor = await self.connection.execute(
            "SELECT chat_id, authorized_at FROM chats"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]  # type: ignore


def auth_required(db: AuthorizedChatsDatabase):
    def decorator(handler: Callable[[Update, CallbackContext], Awaitable[Any]]):
        @wraps(handler)
        async def wrapper(update: Update, context: CallbackContext):
            if not update.effective_chat:
                return

            chat_id = update.effective_chat.id

            async with db.connect() as db_conn:
                if not await db_conn.is_chat_authorized(chat_id):
                    return

            return await handler(update, context)

        return wrapper

    return decorator
