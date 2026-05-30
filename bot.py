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

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (Message, CallbackQuery,
                           InlineKeyboardMarkup, InlineKeyboardButton)
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

PAGE = 15
# кэш последней выдачи /search per chat (в памяти; сбрасывается при передеплое)
_last: dict[int, dict] = {}

# распознаём ссылку объявления любого из порталов → (source, ext_id, label)
import re as _re
_URL_PATTERNS = [
    ("4zida",      _re.compile(r"4zida\.rs/izdavanje-kuca/([^/]+)/[^/]+/([0-9a-f]{24})")),
    ("cityexpert", _re.compile(r"cityexpert\.rs/izdavanje-nekretnina/[^/]+/(\d+)")),
    ("nekretnine", _re.compile(r"nekretnine\.rs/oglasi/(\d+)")),
    ("halooglasi", _re.compile(r"halooglasi\.com/nekretnine/[^\s]*?/(\d{6,})")),
]


def _parse_listing_url(url: str):
    """Из ссылки портала → (source, ext_id, label) или None."""
    for source, rx in _URL_PATTERNS:
        m = rx.search(url)
        if not m:
            continue
        if source == "4zida":
            slug, ext_id = m.group(1), m.group(2)
            label = slug.replace("-gradske-lokacije-novi-sad", "").replace("-", " ").title()
        else:
            ext_id = m.group(1)
            label = source
        return source, ext_id, label
    return None


def _fav_kb(uid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⭐ Сохранить", callback_data=f"fav:{uid}")
    ]])


def _more_kb(remaining: int) -> InlineKeyboardMarkup:
    n = min(PAGE, remaining)
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"Показать ещё {n} →", callback_data="more")
    ]])


async def _send_page(msg: Message, c) -> None:
    """Отправляет следующую страницу из кэша выдачи в чат msg."""
    st = _last.get(msg.chat.id)
    if not st or not st["items"]:
        await msg.answer("Сначала сделай /search.")
        return
    items, off = st["items"], st["offset"]
    index = st.setdefault("index", {})
    batch = items[off:off + PAGE]
    for x in batch:
        index[x.uid] = x                      # чтобы кнопка «Сохранить» нашла объявление
        await msg.answer(x.as_message(c), parse_mode="HTML", reply_markup=_fav_kb(x.uid))
        await asyncio.sleep(0.25)
    st["offset"] = off + len(batch)
    remaining = len(items) - st["offset"]
    if remaining > 0:
        await msg.answer(f"Показано {st['offset']} из {len(items)}.",
                         reply_markup=_more_kb(remaining))
    else:
        await msg.answer(f"Это все {len(items)} объявлений. "
                         f"/monitor on — получать новые автоматически.")

HELP = (
    "🏡 <b>KућaBot</b> — аренда кућа, Нови-Сад + ближайшие.\n\n"
    "/search — найти сейчас (все порталы)\n"
    "/criteria — текущие критерии\n"
    "/set price_max 800 — поле (price_min/price_max/area_min/plot_min/region/deal)\n"
    "/kw dvoriste, garaza — ключевые слова\n"
    "/loc novi sad, petrovaradin, sremska kamenica — приоритет локаций\n"
    "/favorites — сохранённые объявления\n"
    "  (жми ⭐ под объявлением или пришли ссылку — сохраню)\n"
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
        await m.answer("Ничего не нашёл по текущим критериям. "
                       "Попробуй поднять /set price_max или ослабить фильтры.")
        return
    _last[m.chat.id] = {"items": found, "offset": 0}
    await _send_page(m, c)


@dp.callback_query(F.data == "more")
async def cb_more(cb: CallbackQuery):
    await cb.answer()
    # убираем кнопку у предыдущего сообщения, чтобы не плодить дубли
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    c = await storage.get_criteria(cb.message.chat.id)
    await _send_page(cb.message, c)


@dp.callback_query(F.data.startswith("fav:"))
async def cb_fav(cb: CallbackQuery):
    uid = cb.data[len("fav:"):]
    st = _last.get(cb.message.chat.id) or {}
    x = (st.get("index") or {}).get(uid)
    if not x:
        await cb.answer("Не нашёл объявление — сделай /search заново.", show_alert=True)
        return
    await storage.add_favorite(cb.message.chat.id, x.uid, x.url, x.title,
                               x.price, x.location)
    await cb.answer("⭐ Сохранено в избранное")
    try:                       # помечаем кнопку как нажатую
        await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✓ В избранном",
                                                   callback_data="noop")]]))
    except Exception:
        pass


@dp.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


@dp.callback_query(F.data.startswith("unfav:"))
async def cb_unfav(cb: CallbackQuery):
    uid = cb.data[len("unfav:"):]
    await storage.remove_favorite(cb.message.chat.id, uid)
    await cb.answer("Удалено из избранного")
    try:
        await cb.message.edit_text("🗑 <s>удалено из избранного</s>", parse_mode="HTML")
    except Exception:
        pass


@dp.message(Command("favorites", "saved", "fav"))
async def cmd_favorites(m: Message):
    favs = await storage.list_favorites(m.chat.id)
    if not favs:
        await m.answer("В избранном пусто. Жми «⭐ Сохранить» под объявлением "
                       "или пришли мне ссылку на объявление — сохраню.")
        return
    await m.answer(f"⭐ Избранное ({len(favs)}):")
    for f in favs:
        bits = []
        if f["price"]:
            bits.append(f"💶 {f['price']} €")
        if f["location"]:
            bits.append(f"📍 {f['location']}")
        text = f"🏡 <b>{f['title']}</b>\n" + (" · ".join(bits) + "\n" if bits else "")
        text += f'<a href="{f["url"]}">Отворити оглас →</a>'
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"unfav:{f['uid']}")]])
        await m.answer(text, parse_mode="HTML", reply_markup=kb)
        await asyncio.sleep(0.2)


@dp.message(F.text.regexp(r"https?://\S+"))
async def on_listing_link(m: Message):
    """Сохранение объявления по присланной ссылке портала."""
    parsed = _parse_listing_url(m.text)
    if not parsed:
        await m.answer("Это не похоже на ссылку объявления с поддерживаемого "
                       "портала (4zida / cityexpert / nekretnine / halooglasi).")
        return
    source, ext_id, label = parsed
    uid = f"{source}:{ext_id}"
    url = m.text.strip().split()[0]
    await storage.add_favorite(m.chat.id, uid, url, f"{label} [{source}]")
    await m.answer(f"⭐ Сохранил в избранное: <b>{label}</b> [{source}].\n"
                   f"/favorites — весь список.", parse_mode="HTML")


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
