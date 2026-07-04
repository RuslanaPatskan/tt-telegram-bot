import asyncio
import re
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from backend.config import APP_SECRET
from backend import teamtailor, telegram_client


# ── Startup / shutdown ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Прогрів клієнта при старті (не блокує якщо сесія вже є)
    try:
        await telegram_client.get_client()
        print("✅ Telegram UserBot підключено")
    except Exception as e:
        print(f"⚠️  Telegram не підключено: {e}")
    yield


app = FastAPI(title="TT→Telegram bot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # у продакшені замінити на домен панелі
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роздаємо frontend як static files
app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")


# ── Auth helper ─────────────────────────────────────────────────────────────

def verify_secret(x_secret: str | None) -> None:
    if APP_SECRET and x_secret != APP_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Schemas ──────────────────────────────────────────────────────────────────

class CheckRequest(BaseModel):
    candidate_ids: list[str]

    @field_validator("candidate_ids")
    @classmethod
    def non_empty(cls, v):
        if not v:
            raise ValueError("candidate_ids не може бути порожнім")
        if len(v) > 50:
            raise ValueError("Максимум 50 кандидатів за раз")
        return v


class SendRequest(BaseModel):
    candidate_ids: list[str]
    message_template: str
    channel: str = "telegram"
    stage_action: str | None = None  # "next" або None

    @field_validator("message_template")
    @classmethod
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError("Шаблон повідомлення не може бути порожнім")
        return v


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/stages")
async def get_stages(x_secret: Annotated[str | None, Header()] = None):
    verify_secret(x_secret)
    stages = await teamtailor.get_stages()
    return {"stages": stages}


@app.get("/api/debug/tg")
async def debug_tg():
    """Діагностика Telegram з'єднання."""
    try:
        client = await telegram_client.get_client()
        me = await client.get_me()
        return {"ok": True, "user": me.first_name, "username": me.username}
    except Exception as e:
        return {"ok": False, "error": str(e), "type": type(e).__name__}


@app.get("/api/debug/tt/{candidate_id}")
async def debug_tt(candidate_id: str):
    """Діагностика TT API — показує сирий статус і відповідь."""
    import httpx
    from backend.config import TT_API_KEY, TT_BASE_URL, TT_API_VERSION
    url = f"{TT_BASE_URL}/candidates/{candidate_id}"
    headers = {
        "Authorization": f"Token token={TT_API_KEY}",
        "X-Api-Version": TT_API_VERSION,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=headers)
    return {"status": r.status_code, "body": r.text[:1000]}


@app.post("/api/candidates")
async def get_candidates(
    body: CheckRequest,
    x_secret: Annotated[str | None, Header()] = None,
):
    """
    Отримує дані кандидатів з TeamTailor за списком ID.
    Викликається з веб-панелі після того як TeamTailor передав candidate_ids.
    """
    verify_secret(x_secret)
    candidates = await teamtailor.get_candidates_batch(body.candidate_ids)
    return {"candidates": candidates}


@app.post("/api/check")
async def check_telegram(
    body: CheckRequest,
    x_secret: Annotated[str | None, Header()] = None,
):
    """
    Перевіряє наявність кандидатів у Telegram (без відправки).
    Повертає список із полем tg_status: found | not_found | no_phone.
    """
    verify_secret(x_secret)
    candidates = await teamtailor.get_candidates_batch(body.candidate_ids)

    results = []
    for c in candidates:
        phone = c.get("phone", "")
        if not phone:
            results.append({**c, "tg_status": "no_phone"})
            continue

        await asyncio.sleep(1.5)  # пауза між перевірками
        found, _ = await telegram_client.check_telegram(phone, c["first_name"], c.get("last_name", ""))
        results.append({**c, "tg_status": "found" if found else "not_found"})

    return {"results": results}


@app.post("/api/send")
async def send_messages(
    body: SendRequest,
    background_tasks: BackgroundTasks,
    x_secret: Annotated[str | None, Header()] = None,
):
    """
    Запускає відправку повідомлень у фоні.
    Одразу повертає task_id; фронт може поллити /api/status/{task_id}.
    """
    verify_secret(x_secret)

    if len(body.candidate_ids) > 30:
        raise HTTPException(
            status_code=400,
            detail="Максимум 30 кандидатів за раз (ліміт UserBot безпеки)",
        )

    task_id = f"task_{asyncio.get_event_loop().time():.0f}"
    _tasks[task_id] = {"status": "running", "results": []}

    background_tasks.add_task(_run_send_task, task_id, body)
    return {"task_id": task_id, "queued": len(body.candidate_ids)}


# In-memory task store (для продакшену замінити на Redis)
_tasks: dict[str, dict] = {}


async def _run_send_task(task_id: str, body: SendRequest):
    try:
        candidates = await teamtailor.get_candidates_batch(body.candidate_ids)

        for c in candidates:
            text = re.sub(
                r"\{\{(\w+)\}\}",
                lambda m: c.get(m.group(1), ""),
                body.message_template,
            )

            try:
                result = await asyncio.wait_for(
                    telegram_client.check_and_send(c, text), timeout=45
                )
            except asyncio.TimeoutError:
                result = {
                    "candidate_id": c["id"],
                    "status": "failed",
                    "reason": "Timeout — Telegram не відповів за 45 сек",
                }
            except Exception as e:
                result = {
                    "candidate_id": c["id"],
                    "status": "failed",
                    "reason": str(e),
                }

            if result["status"] == "sent" and body.stage_action == "next":
                try:
                    result["stage_moved"] = await teamtailor.move_candidate_to_next_stage(c["id"])
                except Exception as se:
                    result["stage_moved"] = False
                    result["stage_error"] = str(se)

            _tasks[task_id]["results"].append(result)

    except Exception as e:
        _tasks[task_id]["error"] = str(e)
    finally:
        _tasks[task_id]["status"] = "done"


@app.get("/api/status/{task_id}")
async def task_status(
    task_id: str,
    x_secret: Annotated[str | None, Header()] = None,
):
    """Поточний стан задачі відправки."""
    verify_secret(x_secret)
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
