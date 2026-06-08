"""Фоновый мониторинг: опрашивает все источники по критериям каждого чата
и шлёт только новые объявления, отсортированные по приоритету локации
(Нови-Сад первым), затем по цене.
"""
from __future__ import annotations

import asyncio
import logging
import time

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

import storage
import ranking
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


async def refresh_ranking(chat_id: int, c: Criteria) -> tuple[list[dict], list[str]]:
    """Собирает все источники, фильтрует, дедупит, скорит по тирам и
    апсертит в персистентный рейтинг. Возвращает (scored, uid'ы новых)."""
    listings = await collect(c)
    listings = await enrich_and_filter(listings, c, cap=60)
    scored = ranking.rank_all(listings, c)
    new_uids = await storage.upsert_ranked(chat_id, scored)
    return scored, new_uids


# --- ежедневная чистка протухших ---
_GONE_MARKERS = ("nije aktivan", "nije pronađen", "nije pronadjen", "arhiviran",
                 "oglas je istekao", "oglas više nije", "uklonjen", "deaktiviran")


async def _is_gone(url: str, sem: asyncio.Semaphore) -> bool:
    async with sem:
        try:
            html = await fetch_text(url, timeout=12)
        except aiohttp.ClientResponseError as e:
            return e.status in (404, 410)        # объявление удалено
        except Exception:
            return False                          # сеть/таймаут — не трогаем
    return any(m in html.lower() for m in _GONE_MARKERS)


async def cleanup_stale(bot: Bot) -> None:
    """Раз в день: убираем из рейтинга объявления, которых давно нет в выдаче.
    Для 4zida/nekretnine подтверждаем удаление запросом страницы;
    cityexpert/halooglasi (SPA/блок) — по сроку (не видели > 26 ч)."""
    sem = asyncio.Semaphore(6)
    for chat_id in await storage.ranked_chats():
        stale = await storage.stale_ranked(chat_id, older_than_s=20 * 3600)
        if not stale:
            continue
        remove: list[str] = []

        async def _check(row):
            src, uid, url = row["source"], row["uid"], row["url"]
            age = time.time() - row["last_seen"]
            if src in _ENRICHABLE:               # 4zida / nekretnine — подтверждаем
                if await _is_gone(url, sem):
                    remove.append(uid)
            else:                                 # SPA/блок — по сроку
                if age > 26 * 3600:
                    remove.append(uid)

        await asyncio.gather(*[_check(r) for r in stale])
        if remove:
            await storage.remove_ranked(chat_id, remove)
            log.info("чистка: чат %s, удалено %d", chat_id, len(remove))
            try:
                await bot.send_message(
                    chat_id, f"🧹 Убрал из рейтинга {len(remove)} протухших/закрытых "
                             f"объявлений. /rank — актуальный список.")
            except Exception:
                pass


async def poll_once(bot: Bot) -> None:
    chats = await storage.monitored_chats()
    log.info("опрос: %d чатов в мониторинге", len(chats))
    for chat_id in chats:
        c = await storage.get_criteria(chat_id)
        had_ranking = bool(await storage.get_ranked(chat_id))
        scored, new_uids = await refresh_ranking(chat_id, c)
        if not had_ranking:                      # первый прогон — без спама
            log.info("чат %s: инициализация рейтинга (%d)", chat_id, len(scored))
            continue
        new_set = set(new_uids)
        new_items = [d for d in scored if d["listing"].uid in new_set]
        for d in new_items:
            x = d["listing"]
            try:
                await bot.send_message(
                    chat_id, f"🆕 <b>[{d['tier']}]</b> новое в рейтинге:\n" + x.as_message(c),
                    parse_mode="HTML")
                await asyncio.sleep(0.4)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except Exception as e:
                log.warning("не отправил %s в %s: %s", x.uid, chat_id, e)
        if new_items:
            log.info("чат %s: %d новых в рейтинге", chat_id, len(new_items))
