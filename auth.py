"""
Запускати ОДИН РАЗ локально для отримання session-файлу.
Після авторизації скопіювати session/userbot.session на сервер.

    python auth.py
"""
import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

API_ID   = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
PHONE    = os.environ["TG_PHONE"]
SESSION  = os.path.join("session", "userbot")


async def main():
    os.makedirs("session", exist_ok=True)
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(phone=PHONE)

    me = await client.get_me()
    print(f"\n✅ Авторизовано як: {me.first_name} (@{me.username})")
    print(f"   Session файл: {SESSION}.session")
    print("\nТепер скопіюй session/userbot.session на сервер і запускай main.py")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
