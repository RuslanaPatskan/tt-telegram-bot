# TT → Telegram UserBot

Інтеграція TeamTailor ATS з Telegram для масової розсилки кандидатам.

## Структура

```
tt-telegram-bot/
├── backend/
│   ├── main.py            # FastAPI: /api/candidates, /api/check, /api/send, /api/status
│   ├── telegram_client.py # Telethon: check_telegram(), send_message()
│   ├── teamtailor.py      # TT API: get_candidate(), post_note()
│   └── config.py          # Env vars
├── frontend/
│   └── index.html         # Веб-панель рекрутера
├── session/
│   └── userbot.session    # Telethon session (генерується через auth.py)
├── auth.py                # Одноразова авторизація UserBot
├── requirements.txt
├── Procfile               # Railway/Render
└── .env.example
```

## Налаштування

### 1. Отримати Telegram API credentials

Зайти на https://my.telegram.org → API development tools → створити app.  
Записати `api_id` і `api_hash`.

### 2. Налаштувати .env

```bash
cp .env.example .env
# Заповнити TG_API_ID, TG_API_HASH, TG_PHONE, TT_API_KEY, APP_SECRET
```

### 3. Встановити залежності

```bash
pip install -r requirements.txt
```

### 4. Авторизувати UserBot (один раз, локально)

```bash
python auth.py
# Введи код з SMS/Telegram
# Отримаєш session/userbot.session
```

### 5. Запустити локально

```bash
uvicorn backend.main:app --reload
# Панель: http://localhost:8000/app
```

### 6. Деплой на Railway

1. Створи проєкт на railway.app
2. Підключи GitHub репозиторій
3. Додай Environment Variables (з .env)
4. Завантаж `session/userbot.session` через Railway Volume або base64 env var
5. Deploy — Railway сам підхопить Procfile

## API Endpoints

| Method | Path | Опис |
|--------|------|------|
| POST | `/api/candidates` | Отримати дані кандидатів з TT |
| POST | `/api/check` | Перевірити наявність у Telegram |
| POST | `/api/send` | Запустити розсилку (фоново) |
| GET  | `/api/status/{task_id}` | Статус розсилки |

Всі запити потребують заголовка `X-Secret: {APP_SECRET}`.

## TeamTailor Bulk Action

В TeamTailor: Settings → Bulk Actions → New Action  
- Назва: "Надіслати в Telegram"  
- URL: `https://your-app.railway.app/app?ids={{candidate_ids}}`  
- Метод: GET (відкриває панель з вибраними кандидатами)

## Ліміти UserBot

| Обсяг/день | Затримка | Ризик |
|------------|----------|-------|
| до 20      | 3–8 сек  | низький |
| 20–50      | 8–15 сек | середній |
| 50+        | не рекомендовано | бан |

Для великих обсягів → Telegram Business API або Green-API (WhatsApp).
