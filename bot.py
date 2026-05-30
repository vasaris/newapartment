"""KућaBot — поиск и мониторинг аренды кућа (Нови-Сад + ближайшие).

Команды:
  /start              — справка
  /search             — найти сейчас по всем порталам
  /criteria           — показать критерии
  /set <поле> <зн.>   — price_min/price_max/area_min/plot_min/region/deal
  /kw <слова>         — ключевые слова (через запятую)
  /loc <локации>      — приоритет локаций (через запятую, первая — главная)
  /monitor on|off     — фоновый мониторинг с пушем новых
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import storage
import monitor
from config import BOT_TOKEN, POLL_MINUTES
from sources import SOURCES

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

dp = Dispatcher()
NUM_FIELDS = {"price_min", "price_max", "area_min", "plot_min"}
STR_FIELDS = {"region", "deal"}

HELP = (
    "🏡 <b>KућaBot</b> — аренда кућа, Нови-Сад + ближайшие.\n\n"
    "/search — найти сейчас (все порталы)\n"
    "/criteria — текущие критерии\n"
    "/set price_max 800 — поле (price_min/price_max/area_min/plot_min/region/deal)\n"
    "/kw dvoriste, garaza — ключевые слова\n"
    "/loc novi sad, petrovaradin, sremska kamenica — приоритет локаций\n"
    "/monitor on — слать новые автоматически\n"
    "/monitor off — выключить\n\n"
    f"Источники: {', '.join(s.name for s in SOURCES)}"
)


@dp.message(Command("start", "help"))
async def cmd_start(m: Message):
    await m.answer(HELP, parse_mode="HTML")


@dp.message(Command("criteria"))
async def cmd_criteria(m: Message):
    c = await storage.get_criteria(m.chat.id)
    await m.answer(
        "<b>Критерии</b>\n"
        f"Регион (запрос): {c.region}\nТип: {c.deal}\n"
        f"Цена: {c.price_min}–{c.price_max} €\n"
        f"Квадратура от: {c.area_min} m²\nPlac от: {c.plot_min} m²\n"
        f"Ключевые слова: {', '.join(c.keywords) or '—'}\n"
        f"Приоритет локаций: {', '.join(c.priority)}",
        parse_mode="HTML")


@dp.message(Command("set"))
async def cmd_set(m: Message, command: CommandObject):
    if not command.args or len(command.args.split(maxsplit=1)) < 2:
        await m.answer("Пример: <code>/set price_max 800</code>", parse_mode="HTML")
        return
    field, value = command.args.split(maxsplit=1)
    c = await storage.get_criteria(m.chat.id)
    if field in NUM_FIELDS:
        if not value.strip().isdigit():
            await m.answer("Значение должно быть числом")
            return
        setattr(c, field, int(value))
    elif field in STR_FIELDS:
        setattr(c, field, value.strip())
    else:
        await m.answer(f"Неизвестное поле. Доступно: {', '.join(sorted(NUM_FIELDS | STR_FIELDS))}")
        return
    await storage.save_criteria(m.chat.id, c)
    await m.answer(f"✅ {field} = {getattr(c, field)}")


@dp.message(Command("kw"))
async def cmd_kw(m: Message, command: CommandObject):
    c = await storage.get_criteria(m.chat.id)
    c.keywords = [w.strip() for w in (command.args or "").split(",") if w.strip()]
    await storage.save_criteria(m.chat.id, c)
    await m.answer(f"✅ Ключевые слова: {', '.join(c.keywords) or '—'}")


@dp.message(Command("loc"))
async def cmd_loc(m: Message, command: CommandObject):
    locs = [w.strip().lower() for w in (command.args or "").split(",") if w.strip()]
    if not locs:
        await m.answer("Пример: <code>/loc novi sad, petrovaradin, sremska kamenica</code>\n"
                       "Первая локация — главный приоритет.", parse_mode="HTML")
        return
    c = await storage.get_criteria(m.chat.id)
    c.priority = locs
    await storage.save_criteria(m.chat.id, c)
    await m.answer(f"✅ Приоритет локаций: {', '.join(c.priority)}\n"
                   f"(Объявления из «{locs[0]}» помечаются ⭐️ и идут первыми)")


@dp.message(Command("search"))
async def cmd_search(m: Message):
    c = await storage.get_criteria(m.chat.id)
    await m.answer("🔎 Ищу по всем порталам…")
    found = monitor.order(await monitor.collect(c), c)
    if not found:
        await m.answer("Ничего не нашёл. Если порталы точно не пустые — "
                       "проверь селекторы (python -m sources.<portal>).")
        return
    for x in found[:15]:
        await m.answer(x.as_message(c), parse_mode="HTML")
        await asyncio.sleep(0.3)
    await m.answer(f"Готово: {len(found)} объявлений (показал до 15). "
                   f"Включи /monitor on, чтобы получать новые автоматически.")


@dp.message(Command("monitor"))
async def cmd_monitor(m: Message, command: CommandObject):
    arg = (command.args or "").strip().lower()
    if arg not in {"on", "off"}:
        await m.answer("Используй: /monitor on  или  /monitor off")
        return
    await storage.set_monitoring(m.chat.id, arg == "on")
    await m.answer(
        f"🟢 Мониторинг включён, проверяю каждые {POLL_MINUTES} мин — пришлю только новое."
        if arg == "on" else "⚪️ Мониторинг выключен.")


async def main():
    await storage.init()
    bot = Bot(BOT_TOKEN)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(monitor.poll_once, "interval",
                      minutes=POLL_MINUTES, args=[bot], id="poll")
    scheduler.start()
    log.info("планировщик запущен, интервал %d мин, источников: %d",
             POLL_MINUTES, len(SOURCES))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
