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

log = logging.getLogger("monitor")


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
