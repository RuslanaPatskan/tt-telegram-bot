"""
Запускати ОДИН РАЗ локально для отримання рядка сесії (TG_SESSION_STRING).
Хостинги без постійного диска (наприклад, Render) не зберігають файл
session/userbot.session, тому сесію передають змінною середовища.

    python gen_session_string.py

Рядок сесії дає повний доступ до акаунта — нікому його не показуй
і не додавай у репозиторій.
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


async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start(phone=PHONE)

    me = await client.get_me()
    print(f"\n✅ Авторизовано як: {me.first_name} (@{me.username})")
    print("\nTG_SESSION_STRING (скопіюй у змінні середовища хостингу):\n")
    print(client.session.save())

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
