"""Источник: cityexpert.rs — через их внутренний JSON-API (РАБОТАЕТ).

cityexpert — Angular SPA, HTML парсить нельзя, но есть чистый JSON-API:
    GET https://cityexpert.rs/api/Search?req={JSON}
где req — URL-кодированный объект фильтров. Подтверждено из DevTools:
    ptId=[2]  → кућа        cityId=2 → Нови-Сад      rentOrSale="r" → издавање
Доп. фильтры: minPrice / maxPrice / minSize, сортировка sort="datedsc".
В НС кућа немного (~11), помещаются на одну страницу.

Поле otherArray содержит adpGarden = двориште (отмечаем в выводе).
"""
from __future__ import annotations

import json
import asyncio
import urllib.parse
import aiohttp

from .base import Source, Listing, Criteria, UA

API = "https://cityexpert.rs/api/Search"
SITE = "https://cityexpert.rs"
CITY_ID = {"novi-sad": 2, "beograd": 1, "nis": 3}   # достаточно для НС
PT_HOUSE = 2                                          # тип = кућа (подтверждён)

# транслитерация сербской латиницы для slug ссылки
_TR = str.maketrans({"š": "s", "đ": "dj", "č": "c", "ć": "c", "ž": "z",
                     "Š": "s", "Đ": "dj", "Č": "c", "Ć": "c", "Ž": "z"})


def _slug(*parts: str) -> str:
    s = " ".join(p for p in parts if p).lower().translate(_TR)
    return "".join(ch if ch.isalnum() or ch == " " else "" for ch in s).strip().replace(" ", "-")


class CityExpert(Source):
    name = "cityexpert"

    def _req_url(self, c: Criteria, page: int = 1) -> str:
        req = {
            "ptId": [PT_HOUSE],
            "cityId": CITY_ID.get(c.region, 2),
            "rentOrSale": "r",
            "searchSource": "regular",
            "sort": "datedsc",
            "currentPage": page,
        }
        if c.price_max:
            req["maxPrice"] = c.price_max
        if c.price_min:
            req["minPrice"] = c.price_min
        if c.area_min:
            req["minSize"] = c.area_min
        q = urllib.parse.quote(json.dumps(req, separators=(",", ":")))
        return f"{API}?req={q}"

    def _parse_json(self, data: dict, region: str) -> list[Listing]:
        out = []
        for it in data.get("result", []):
            muni = it.get("municipality") or ""
            polys = [p for p in (it.get("polygons") or []) if p and p != muni]
            location = ", ".join([muni] + polys) or muni or "Novi Sad"
            garden = "adpGarden" in (it.get("otherArray") or [])
            prop_id = it.get("propId")
            street = it.get("street") or "Kuća"
            url = (f"{SITE}/izdavanje-nekretnina/{region}/{prop_id}/"
                   f"{_slug(street, muni)}")
            price = it.get("price")
            size = it.get("size")
            pets = it.get("petsArray") or []
            out.append(Listing(
                source=self.name,
                ext_id=str(it.get("uniqueID") or prop_id),
                title=f"Kuća, {street}",
                url=url,
                price=int(price) if isinstance(price, (int, float)) else None,
                area_m2=int(size) if isinstance(size, (int, float)) else None,
                location=location,
                heating=("dvorište" if garden else None),
                has_yard=True if garden else None,
                pets_ok=True if pets else None,
            ))
        return out

    async def search(self, c: Criteria, limit: int = 40) -> list[Listing]:
        res, page = [], 1
        async with aiohttp.ClientSession() as s:
            while len(res) < limit and page <= 5:
                url = self._req_url(c, page)
                try:
                    async with s.get(url, headers={"User-Agent": UA,
                                     "Accept": "application/json"},
                                     timeout=aiohttp.ClientTimeout(total=20)) as r:
                        r.raise_for_status()
                        data = await r.json(content_type=None)
                except Exception:
                    break
                batch = self._parse_json(data, c.region)
                if not batch:
                    break
                res.extend(batch)
                # на cityexpert кућа мало — обычно одна страница
                if len(batch) < 10:
                    break
                page += 1
        return [x for x in res if x.matches(c)][:limit]


if __name__ == "__main__":
    async def _d():
        src, c = CityExpert(), Criteria(price_max=5000)
        print("[i] URL:", src._req_url(c))
        items = await src.search(c)
        print(f"[i] объявлений: {len(items)}")
        for x in sorted(items, key=lambda z: c.rank(z.location))[:5]:
            print("-" * 50); print(x.as_message(c))
    asyncio.run(_d())
