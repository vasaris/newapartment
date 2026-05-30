"""Фоновый мониторинг: опрашивает все источники по критериям каждого чата
и шлёт только новые объявления, отсортированные по приоритету локации
(Нови-Сад первым), затем по цене.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

import storage
from sources import SOURCES, Criteria, Listing
from sources.base import fetch_text

log = logging.getLogger("monitor")

import re as _re
import html as _html
_OGDESC_RX = _re.compile(
    r'<meta[^>]*(?:property|name)=["\']og:description["\'][^>]*>', _re.I)
_CONTENT_RX = _re.compile(r'content=["\']([^"\']*)["\']', _re.I)
# куда есть смысл ходить за описанием: SSR-страницы с og:description.
# cityexpert (SPA, общий og) и halooglasi (блок бот-фетча) пропускаем.
_ENRICHABLE = {"4zida", "nekretnine"}


async def _fetch_desc(x: Listing, sem: asyncio.Semaphore) -> None:
    if x.desc or x.source not in _ENRICHABLE:
        return
    async with sem:
        try:
            html = await fetch_text(x.url, timeout=12)
        except Exception:
            return
    m = _OGDESC_RX.search(html)
    if not m:
        return
    cm = _CONTENT_RX.search(m.group(0))
    if cm:
        x.desc = _html.unescape(cm.group(1))


async def enrich_and_filter(listings: list[Listing], c: Criteria,
                            cap: int = 30) -> list[Listing]:
    """Дотягивает описание у верхушки выдачи и выкидывает исключённые
    (этаж/юрлица/общага). Хвост за пределами cap оставляем как есть."""
    head, tail = listings[:cap], listings[cap:]
    sem = asyncio.Semaphore(8)
    await asyncio.gather(*[_fetch_desc(x, sem) for x in head])
    head = [x for x in head if not x.is_excluded()]
    return head + tail


async def collect(c: Criteria) -> list[Listing]:
    """Опрос всех источников; один упавший не валит остальные."""
    out: list[Listing] = []
    results = await asyncio.gather(
        *[src.search(c, limit=40) for src in SOURCES], return_exceptions=True)
    for src, r in zip(SOURCES, results):
        if isinstance(r, Exception):
            log.warning("источник %s упал: %s", src.name, r)
        else:
            out.extend(r)
    return out


def order(listings: list[Listing], c: Criteria) -> list[Listing]:
    """Сортировка: сначала подтверждённые «двор/собака» (dog_score), затем
    Нови-Сад и ближайшие по приоритету, внутри — по возрастанию цены."""
    return sorted(listings, key=lambda x: (-x.dog_score(), c.rank(x.location),
                                           x.price or 10**9))


async def poll_once(bot: Bot) -> None:
    chats = await storage.monitored_chats()
    log.info("опрос: %d чатов в мониторинге", len(chats))
    for chat_id in chats:
        c = await storage.get_criteria(chat_id)
        listings = await collect(c)
        by_uid = {x.uid: x for x in listings}
        new_uids = await storage.filter_new(chat_id, list(by_uid))
        # первичная инициализация чата — без спама всей выдачей
        if (len(by_uid) - len(new_uids)) == 0 and new_uids:
            await storage.mark_seen(chat_id, list(by_uid))
            log.info("чат %s: инициализация (%d), без пуша", chat_id, len(by_uid))
            continue
        new_items = order([by_uid[u] for u in new_uids], c)
        new_items = await enrich_and_filter(new_items, c, cap=len(new_items))
        for x in new_items:
            try:
                await bot.send_message(chat_id, x.as_message(c), parse_mode="HTML")
                await asyncio.sleep(0.4)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except Exception as e:
                log.warning("не отправил %s в %s: %s", x.uid, chat_id, e)
        await storage.mark_seen(chat_id, list(new_uids))
        if new_items:
            log.info("чат %s: отправлено %d новых", chat_id, len(new_items))
