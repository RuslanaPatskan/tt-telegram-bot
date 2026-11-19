import asyncio
import random
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact, User
from telethon.errors import (
    FloodWaitError,
    UsernameNotOccupiedError,
    UsernameInvalidError,
    PhoneNumberInvalidError,
    InputUserDeactivatedError,
    UserNotMutualContactError,
    PeerFloodError,
)
from backend.config import TG_API_ID, TG_API_HASH, SESSION_PATH, TG_SESSION_STRING
from backend import teamtailor

# Глобальний клієнт — ініціалізується один раз при старті
_client: TelegramClient | None = None


async def get_client() -> TelegramClient:
    global _client
    if _client is None or not _client.is_connected():
        session = StringSession(TG_SESSION_STRING.strip()) if TG_SESSION_STRING else SESSION_PATH
        _client = TelegramClient(session, TG_API_ID, TG_API_HASH)
        await _client.connect()
        if not await _client.is_user_authorized():
            raise RuntimeError(
                "Сесія Telegram не авторизована. "
                "Запусти auth.py локально для отримання session-файлу."
            )
    return _client


async def check_telegram(phone: str, first_name: str, last_name: str = "") -> tuple[bool, object | None]:
    """
    Перевіряє чи є номер в Telegram.
    Повертає (True, user) або (False, None).
    Не залишає контакт у списку — видаляє після перевірки.
    """
    client = await get_client()

    result = await client(ImportContactsRequest([
        InputPhoneContact(
            client_id=0,
            phone=phone,
            first_name=first_name,
            last_name=last_name,
        )
    ]))

    if not result.users:
        return False, None

    return True, result.users[0]


async def resolve_username(username: str):
    """Знаходить користувача Telegram за ніком (без імпорту контакту). None якщо немає."""
    client = await get_client()
    try:
        entity = await client.get_entity(username)
    except (UsernameNotOccupiedError, UsernameInvalidError, ValueError):
        return None
    if isinstance(entity, User) and not entity.bot:
        return entity
    return None


async def find_user(candidate: dict) -> tuple[object | None, str | None]:
    """
    Шукає кандидата в Telegram: спочатку за телефоном, якщо не знайдено
    (або телефону немає) — за ніком з кастомного поля Teamtailor.
    Повертає (user, "phone" | "username") або (None, None).
    """
    phone = candidate.get("phone") or ""
    username = candidate.get("tg_username") or ""

    if phone:
        found, user = await check_telegram(
            phone, candidate.get("first_name", ""), candidate.get("last_name", "")
        )
        if found:
            return user, "phone"
        # За телефоном не знайшли — пробуємо нік, якщо він є в картці
        username = username or await teamtailor.get_candidate_tg_username(candidate["id"])

    if username:
        await asyncio.sleep(random.uniform(1.0, 2.0))
        user = await resolve_username(username)
        if user:
            return user, "username"

    return None, None


async def send_message(phone_or_user, text: str) -> dict:
    """
    Надсилає повідомлення. Приймає user-об'єкт або рядок з номером.
    Повертає {"ok": True} або {"ok": False, "reason": "..."}.
    """
    client = await get_client()
    try:
        await client.send_message(phone_or_user, text)
        return {"ok": True}
    except FloodWaitError as e:
        wait = e.seconds + 5
        await asyncio.sleep(wait)
        # Одна повторна спроба після очікування
        try:
            await client.send_message(phone_or_user, text)
            return {"ok": True}
        except Exception as retry_err:
            return {"ok": False, "reason": f"FloodWait retry failed: {retry_err}"}
    except InputUserDeactivatedError:
        return {"ok": False, "reason": "Акаунт Telegram видалено або заблоковано"}
    except UserNotMutualContactError:
        return {"ok": False, "reason": "Не вдалося надіслати: обмеження приватності"}
    except PhoneNumberInvalidError:
        return {"ok": False, "reason": "Невірний формат номера телефону"}
    except PeerFloodError:
        return {"ok": False, "reason": "PeerFlood — забагато нових контактів, пауза потрібна"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


async def check_and_send(candidate: dict, text: str) -> dict:
    """
    Повний pipeline для одного кандидата:
    1. Перевірка наявності в Telegram
    2. Надсилання (якщо є)
    Повертає результат із усіма деталями.
    """
    phone = candidate.get("phone") or ""
    username = candidate.get("tg_username") or ""

    if not phone and not username:
        return {
            "candidate_id": candidate["id"],
            "status": "skipped",
            "reason": "Немає номера телефону і Telegram-ніка",
        }

    # Затримка перед перевіркою (щоб не тригерити антиспам)
    await asyncio.sleep(random.uniform(1.5, 3.0))

    tg_user, via = await find_user(candidate)

    if tg_user is None:
        return {
            "candidate_id": candidate["id"],
            "status": "not_in_telegram",
            "reason": "Не знайдено в Telegram за телефоном або ніком",
        }

    # Затримка перед відправкою
    await asyncio.sleep(random.uniform(4.0, 9.0))

    result = await send_message(tg_user, text)

    return {
        "candidate_id": candidate["id"],
        "status": "sent" if result["ok"] else "failed",
        "reason": result.get("reason"),
        "tg_username": getattr(tg_user, "username", None),
        "found_by": via,
    }
