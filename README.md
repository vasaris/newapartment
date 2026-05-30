# KućaBot — мониторинг аренды кућа (Нови-Сад + ближайшие)

Telegram-бот (aiogram 3): ищет куће за издавање по порталам и присылает
**только новые** объявления, приоритет — Нови-Сад. Стек как у FinBot:
aiogram 3 + APScheduler + SQLite, деплой на Railway.

## Статус источников (проверено на живых страницах 30.05.2026)
| Портал | Рендеринг | Статус | Примечание |
|--------|-----------|--------|------------|
| **4zida.rs** | SSR | ✅ работает | основной, ≈200+ кућа в НС; парс по паттерну ссылки |
| **cityexpert.rs** | Angular SPA | ✅ работает | через JSON-API `/api/Search?req={...}` (ptId=2=кућа) |
| **halooglasi.com** | SSR | ✅ работает | может блокировать IP дата-центров (Railway) |
| **nekretnine.rs** | SSR (новый URL) | ✅ работает | `/izdavanje-samostalnih-kuca/{grad}/`, парс по `/oglasi/{id}/` |

cityexpert парсится не из HTML (это Angular SPA), а через его внутренний
JSON-API: `GET https://cityexpert.rs/api/Search?req={JSON}` с фильтрами
`ptId=[2]` (кућа), `cityId=2` (НС), `rentOrSale="r"`. Реализовано и проверено.

nekretnine.rs парсится из HTML, но только в НОВОМ формате URL
(`/izdavanje-samostalnih-kuca/novi-sad/`) — старый `/stambeni-objekti/...`
редиректит на главную. Тип = самостојећа кућа (idTipologia=7).

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
python -m sources.fourzida      # ~40 объявлений
python -m sources.cityexpert    # ~11 кућа (JSON-API)
python -m sources.nekretnine    # ~33 самостојеће куће (SSR)
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
  cityexpert.py   — ✅ источник через JSON-API
  nekretnine.py   — ✅ источник SSR (паттерн /oglasi/)
```
