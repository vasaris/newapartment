# KućaBot — мониторинг аренды кућа (Нови-Сад + ближайшие)

Telegram-бот (aiogram 3): ищет куће за издавање по порталам и присылает
**только новые** объявления, приоритет — Нови-Сад. Стек как у FinBot:
aiogram 3 + APScheduler + SQLite, деплой на Railway.

## Статус источников (проверено на живых страницах 30.05.2026)
| Портал | Рендеринг | Статус | Примечание |
|--------|-----------|--------|------------|
| **4zida.rs** | SSR | ✅ работает | основной, ≈200+ кућа в НС; парс по паттерну ссылки |
| **halooglasi.com** | SSR | ✅ работает | может блокировать IP дата-центров (Railway) |
| **cityexpert.rs** | Angular SPA | ⏸ заглушка | в HTML только оболочка → нужен JSON-API |
| **nekretnine.rs** | Next.js SPA | ⏸ заглушка | список редиректит на главную → нужен JSON-API |

cityexpert и nekretnine простым `aiohttp + bs4` не парсятся — это архитектура
сайтов, а не вопрос селекторов. Они оставлены готовыми заглушками с пошаговой
инструкцией, как подключить их внутренний JSON-API (ловится в DevTools→Network
за 5 минут) — см. докстринги в `sources/cityexpert.py` и `sources/nekretnine.py`.
После реализации API раскомментируй их в `sources/__init__.py`.

> Про **ptId** для кућа на cityexpert: на SPA он не в URL страницы, а в теле
> XHR-запроса к API. Возьмёшь точное значение из payload в DevTools.

## Как работают локации и приоритет
4zida отдаёт локацию прямо в ссылке объявления
(`/izdavanje-kuca/sirine-petrovaradin-…-novi-sad/...`), поэтому Петроварадin,
Сремска Каменица, Ветерник, Футог распознаются точно. `priority[0]` — главный
город (Нови-Сад, помечается ⭐️ и идёт первым), остальные — тиры по порядку.
Внутри тира сортировка по возрастанию цены.
Менять: `/loc novi sad, petrovaradin, sremska kamenica, veternik, futog`
(первая — главная локация).

## Команды
- `/search` — найти сейчас по активным порталам
- `/criteria` — текущие критерии
- `/set price_max 800` — поле (`price_min/price_max/area_min/plot_min/region/deal`)
- `/kw dvoriste, garaza` — ключевые слова
- `/loc novi sad, petrovaradin, …` — приоритет локаций (первая = главная)
- `/monitor on` / `off` — фоновый мониторинг с пушем

## Запуск
```bash
pip install -r requirements.txt
cp .env.example .env        # вставь BOT_TOKEN от @BotFather
export $(cat .env | xargs)
python bot.py
```

Проверить парсер портала на живой странице:
```bash
python -m sources.fourzida      # должен распознать ~40 объявлений
python -m sources.halooglasi
```

## Деплой на Railway
1. Репо на GitHub → Railway → Deploy from repo.
2. Variables: `BOT_TOKEN`, опц. `POLL_MINUTES` (по умолчанию 30).
3. Start command из `Procfile` (`worker: python bot.py`).
4. ⚠️ SQLite эфемерна между деплоями — подключи Railway Volume под `kuca.db`
   или переедь на Postgres (меняется только `storage.py`).
5. Если halooglasi с Railway отдаёт пусто/403 — это блок по IP дата-центра,
   оставь только 4zida.

## Структура
```
bot.py            — хендлеры aiogram + планировщик
monitor.py        — опрос источников, дедуп, сортировка, пуш
storage.py        — SQLite: критерии + виденные объявления
config.py         — BOT_TOKEN, POLL_MINUTES
sources/
  base.py         — Listing/Criteria, rank(), fetch-хелпер, Source ABC
  fourzida.py     — ✅ основной парсер (по паттерну ссылки)
  halooglasi.py   — ✅ парсер .product-item
  cityexpert.py   — ⏸ заглушка + инструкция под JSON-API
  nekretnine.py   — ⏸ заглушка + инструкция под JSON-API
```
