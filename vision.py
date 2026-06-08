"""Vision-оценка фото объявления через Claude Haiku.

Берёт 1-3 фото объявления и возвращает оценку «жилого вида»:
  q (1..5): 5 = можно заезжать, свежо/опрятно; 1 = пусто/убито/старьё «бабушка-Югославия».
  empty: пусто (нет мебели);  dated: устаревший «социалистический» интерьер.

Работает только если задан ANTHROPIC_API_KEY (иначе вернёт None → фото не влияют).
Дёшево: Haiku 4.5, ~полцента за объявление. Кэш по uid делает второй прогон бесплатным.
"""
from __future__ import annotations

import os
import json
import asyncio
import aiohttp

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("VISION_MODEL", "claude-haiku-4-5-20251001")
# сколько кадров слать на анализ: берём равномерно по всей галерее (не первые N,
# чтобы не смотреть только фасад). Поднимай через переменную MAX_PHOTOS.
MAX_PHOTOS = int(os.environ.get("MAX_PHOTOS", "12"))


def _sample(photos: list[str]) -> list[str]:
    if len(photos) <= MAX_PHOTOS:
        return photos
    step = len(photos) / MAX_PHOTOS
    return [photos[int(i * step)] for i in range(MAX_PHOTOS)]

_PROMPT = (
    "These are photos of a house/apartment listed for rent. The tenant wants a "
    "MOVE-IN-READY home with a decent, modern renovation — not empty, not a dated "
    "socialist-era ('Yugoslavia grandma') interior. Judge ONLY from the photos. "
    "Reply with STRICT JSON, no prose: "
    '{"livable": <1-5 int>, "empty": <true|false>, "dated": <true|false>, '
    '"note": "<max 8 words>"}. '
    "livable 5 = furnished, modern, well-kept, ready to live; "
    "3 = ok but plain/worn; 1 = empty or derelict or very dated."
)


def available() -> bool:
    return bool(API_KEY)


async def analyze(photos: list[str], sem: asyncio.Semaphore) -> dict | None:
    if not API_KEY or not photos:
        return None
    content = [{"type": "image", "source": {"type": "url", "url": u}}
               for u in _sample(photos)]
    content.append({"type": "text", "text": _PROMPT})
    body = {"model": MODEL, "max_tokens": 90,
            "messages": [{"role": "user", "content": content}]}
    headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    async with sem:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(API_URL, headers=headers, json=body,
                                  timeout=aiohttp.ClientTimeout(total=45)) as r:
                    r.raise_for_status()
                    data = await r.json()
        except Exception:
            return None
    return _parse(data)


def _parse(data: dict) -> dict | None:
    txt = "".join(b.get("text", "") for b in data.get("content", [])
                  if b.get("type") == "text")
    try:
        j = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
        q = float(j.get("livable", 3))
        return {"q": max(1.0, min(5.0, q)),
                "empty": bool(j.get("empty", False)),
                "dated": bool(j.get("dated", False))}
    except Exception:
        return None
