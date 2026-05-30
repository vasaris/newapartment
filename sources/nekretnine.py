"""Источник: nekretnine.rs — ЗАГЛУШКА (по умолчанию отключён).

⚠️ Проверено на живой странице: nekretnine.rs — это Next.js SPA. Прямой
HTTP-запрос к списку редиректит на главную и отдаёт только навигационную
оболочку (статика на s1.nekretnine.rs/_next/...), объявлений в сыром HTML нет.
Значит aiohttp + bs4 не подходит.

КАК ВКЛЮЧИТЬ (нужен их API / Next data, 5 минут в DevTools):
  1. Открой страницу списка, F12 → Network → Fetch/XHR.
     Рабочий URL списка (подтверждён):
     https://www.nekretnine.rs/stambeni-objekti/kuce/izdavanje-prodaja/izdavanje/grad/novi-sad/lista/po-stranici/20/
  2. Найди XHR с JSON-списком объявлений (или запрос вида
     /_next/data/<buildId>/...json). Скопируй URL и формат ответа.
  3. Реализуй запрос в search() (aiohttp .get/.post), распарсь JSON в Listing,
     раскомментируй Nekretnine в sources/__init__.py.

Замечание по локациям: на nekretnine.rs Петроварадин/Сремска Каменица/
Сремски Карловци — ОТДЕЛЬНЫЕ grad, а не часть «novi-sad». Чтобы их ловить,
дёрни API ещё раз с grad=petrovaradin и т.д. (Ветерник/Футог входят в novi-sad).
"""
from __future__ import annotations

import logging
from .base import Source, Listing, Criteria

log = logging.getLogger("nekretnine")
BASE = "https://www.nekretnine.rs"


class Nekretnine(Source):
    name = "nekretnine"
    _warned = False

    def _list_url(self, c: Criteria, per_page: int = 20, page: int = 1) -> str:
        url = (f"{BASE}/stambeni-objekti/kuce/izdavanje-prodaja/izdavanje"
               f"/grad/{c.region}/lista/po-stranici/{per_page}/")
        if page > 1:
            url += f"stranica/{page}/"
        return url

    async def search(self, c: Criteria, limit: int = 40) -> list[Listing]:
        if not Nekretnine._warned:
            log.warning("nekretnine.rs отключён: SPA, нужен JSON-API "
                        "(см. инструкцию в sources/nekretnine.py). Возвращаю [].")
            Nekretnine._warned = True
        return []
