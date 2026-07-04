import httpx
from backend.config import TT_API_KEY, TT_BASE_URL, TT_API_VERSION
from typing import Optional
import datetime


def _headers() -> dict:
    return {
        "Authorization": f"Token token={TT_API_KEY}",
        "X-Api-Version": TT_API_VERSION,
        "Content-Type": "application/vnd.api+json",
    }


async def get_candidate(candidate_id: str) -> Optional[dict]:
    """Повертає {id, first_name, last_name, phone} або None."""
    url = f"{TT_BASE_URL}/candidates/{candidate_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200:
            return None
        data = r.json()["data"]
        attrs = data["attributes"]
        return {
            "id": data["id"],
            "first_name": attrs.get("first-name", ""),
            "last_name":  attrs.get("last-name", ""),
            "phone":      attrs.get("phone", ""),
            "email":      attrs.get("email", ""),
        }


async def get_candidates_batch(candidate_ids: list[str]) -> list[dict]:
    """Запитує всіх кандидатів паралельно, пропускає не знайдених."""
    import asyncio
    results = await asyncio.gather(
        *[get_candidate(cid) for cid in candidate_ids],
        return_exceptions=False,
    )
    return [r for r in results if r is not None]


async def post_note(candidate_id: str, body: str) -> bool:
    """Додає замітку в картку кандидата. Повертає True якщо успішно."""
    url = f"{TT_BASE_URL}/notes"
    payload = {
        "data": {
            "type": "notes",
            "attributes": {"body": body},
            "relationships": {
                "candidate": {
                    "data": {"type": "candidates", "id": candidate_id}
                }
            },
        }
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=_headers(), json=payload)
        return r.status_code in (200, 201)


def build_note_text(message_text: str, channel: str = "Telegram") -> str:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"📨 Надіслано повідомлення в {channel}: «{message_text}» · {ts}"


async def get_stages() -> list[dict]:
    """Повертає всі етапи з TeamTailor."""
    url = f"{TT_BASE_URL}/stages"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200:
            return []
        items = r.json().get("data", [])
        return [
            {"id": item["id"], "name": item["attributes"].get("name", "")}
            for item in items
        ]


async def move_to_stage(job_application_id: str, stage_id: str) -> bool:
    """Переводить job-application на вказаний етап."""
    url = f"{TT_BASE_URL}/job-applications/{job_application_id}"
    payload = {
        "data": {
            "type": "job-applications",
            "id": job_application_id,
            "relationships": {
                "stage": {"data": {"type": "stages", "id": stage_id}}
            },
        }
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.patch(url, headers=_headers(), json=payload)
        return r.status_code in (200, 204)


async def move_candidate_to_next_stage(candidate_id: str) -> bool:
    """Знаходить поточний етап кандидата і переводить на наступний."""
    # 1. Отримуємо job-applications з поточним stage і job
    url = f"{TT_BASE_URL}/candidates/{candidate_id}/job-applications"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200:
            return False
        apps = r.json().get("data", [])

    success = False
    for app in apps:
        app_id = app["id"]
        rel = app.get("relationships", {})
        current_stage_id = rel.get("stage", {}).get("data", {}) .get("id")
        job_id = rel.get("job", {}).get("data", {}).get("id")
        if not current_stage_id or not job_id:
            continue

        # 2. Отримуємо всі етапи цієї вакансії
        async with httpx.AsyncClient(timeout=10) as client:
            sr = await client.get(f"{TT_BASE_URL}/jobs/{job_id}/stages", headers=_headers())
            if sr.status_code != 200:
                continue
            stages = sr.json().get("data", [])

        stage_ids = [s["id"] for s in stages]
        if current_stage_id not in stage_ids:
            continue
        idx = stage_ids.index(current_stage_id)
        if idx + 1 >= len(stage_ids):
            continue  # вже останній етап

        if await move_to_stage(app_id, stage_ids[idx + 1]):
            success = True

    return success
