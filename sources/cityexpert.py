"""Источник: cityexpert.rs — ЗАГЛУШКА (по умолчанию отключён).

⚠️ Проверено на живой странице: cityexpert — это client-side Angular SPA.
В сыром HTML приходит только мета-оболочка (<title>City Expert</title>),
объявлений там НЕТ — они грузятся JS-запросом после загрузки страницы.
Поэтому aiohttp + bs4 здесь не работает в принципе.

КАК ВКЛЮЧИТЬ (нужен их внутренний JSON-API, 5 минут в DevTools):
  1. Открой https://cityexpert.rs/izdavanje-nekretnina/novi-sad, F12 → Network → Fetch/XHR.
  2. Применить фильтр (тип = Kuća). Найди XHR-запрос, который возвращает JSON
     со списком объявлений (обычно POST на /api/Search/ или похожий путь).
  3. Скопируй URL запроса, метод, и тело (payload) — там будет поле типа
     ptId/propertyType для кућа (на сайте видно, что кућа — отдельный тип).
  4. Впиши запрос в search() ниже (aiohttp .post(api_url, json=payload)),
     распарсь JSON в Listing, и раскомментируй CityExpert в sources/__init__.py.

Поле ptId, про которое спрашивал: его реальное значение возьмёшь из payload
того самого XHR — на SPA оно не в URL страницы, а в теле API-запроса.
"""
from __future__ import annotations

import logging
from .base import Source, Listing, Criteria

log = logging.getLogger("cityexpert")
BASE = "https://cityexpert.rs"


class CityExpert(Source):
    name = "cityexpert"
    _warned = False

    async def search(self, c: Criteria, limit: int = 40) -> list[Listing]:
        if not CityExpert._warned:
            log.warning("cityexpert отключён: SPA, нужен JSON-API "
                        "(см. инструкцию в sources/cityexpert.py). Возвращаю [].")
            CityExpert._warned = True
        return []

        # --- ШАБЛОН под их JSON-API (раскомментируй и допили после DevTools) ---
        # import aiohttp, json
        # from .base import UA, to_int
        # api = "https://cityexpert.rs/api/Search/"          # ← из DevTools
        # payload = {                                         # ← из DevTools
        #     "ptId": [2],            # тип = кућа (подтверди значение!)
        #     "cityId": 2,            # Нови-Сад
        #     "rentOrSale": "r",      # издавање
        #     "maxPrice": c.price_max or None,
        #     "minPrice": c.price_min or None,
        #     "minSize": c.area_min or None,
        #     "currentPage": 1, "resultsPerPage": 60,
        # }
        # async with aiohttp.ClientSession() as s:
        #     async with s.post(api, json=payload, headers={"User-Agent": UA}) as r:
        #         data = await r.json()
        # out = []
        # for it in data.get("result", []):
        #     out.append(Listing(
        #         source=self.name, ext_id=str(it["id"]),
        #         title=it.get("street") or "CityExpert",
        #         url=f"{BASE}/izdavanje-nekretnina/novi-sad/{it['id']}/{it.get('seoUrl','')}",
        #         price=to_int(str(it.get("price"))),
        #         area_m2=to_int(str(it.get("size"))),
        #         location=", ".join(filter(None, [it.get("street"), it.get("municipality"), "Novi Sad"])),
        #     ))
        # return [x for x in out if x.matches(c)][:limit]
