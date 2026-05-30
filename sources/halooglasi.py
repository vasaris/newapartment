"""Источник: halooglasi.com (server-rendered, aiohttp + bs4).

Самый дружелюбный к скраперу портал. URL: /nekretnine/{deal}/{region}.
⚠️ halooglasi иногда блокирует запросы с дата-центров (bot-детект). Локально
обычно ок; на Railway если ловишь пустые ответы/403 — это блок по IP, тогда
оставь в реестре только 4zida (или гоняй через прокси/резидентный IP).

⚠️ Селекторы (.product-item и дочерние) проставлены по типовой структуре —
сверь живой DOM:  python -m sources.halooglasi
"""
from __future__ import annotations

import asyncio
from bs4 import BeautifulSoup

from .base import Source, Listing, Criteria, fetch_text, to_int

BASE = "https://www.halooglasi.com"


class HaloOglasi(Source):
    name = "halooglasi"

    def _url(self, c: Criteria, page: int = 1) -> str:
        url = f"{BASE}/nekretnine/{c.deal}/{c.region}"
        p = ["cena_d_unit=4", f"page={page}"]
        if c.price_min:
            p.append(f"cena_d_from={c.price_min}")
        if c.price_max:
            p.append(f"cena_d_to={c.price_max}")
        if c.area_min:
            p.append(f"kvadratura_d_from={c.area_min}")
        return url + "?" + "&".join(p)

    def _parse(self, html: str) -> list[Listing]:
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for card in soup.select("div.product-item"):
            a = card.select_one("h3.product-title a") or card.select_one("a.title")
            if not a or not a.get("href"):
                continue
            href = a["href"]
            url = href if href.startswith("http") else BASE + href
            ext_id = url.rstrip("/").split("/")[-1].split("?")[0]
            price_el = card.select_one(".central-feature i") or card.select_one(".central-feature")
            loc_el = card.select_one(".subtitle-places") or card.select_one(".subtitle")
            area = plot = None
            for li in card.select(".product-features li, .value-wrapper"):
                t = li.get_text(" ", strip=True).lower()
                if "plac" in t or ("ar" in t and "kvadrat" not in t):
                    plot = plot or to_int(t)
                elif "m2" in t or "m²" in t or "kvadrat" in t:
                    area = area or to_int(t)
            img = card.select_one("img")
            out.append(Listing(
                source=self.name, ext_id=ext_id, title=a.get_text(strip=True), url=url,
                price=to_int(price_el.get_text() if price_el else None),
                area_m2=area, plot_m2=plot,
                location=loc_el.get_text(" ", strip=True) if loc_el else None,
                image=(img.get("data-src") or img.get("src")) if img else None,
            ))
        return out

    async def search(self, c: Criteria, limit: int = 40) -> list[Listing]:
        res, page = [], 1
        while len(res) < limit and page <= 5:
            try:
                html = await fetch_text(self._url(c, page))
            except Exception:
                break
            batch = self._parse(html)
            if not batch:
                break
            res.extend(batch)
            page += 1
        return [x for x in res if x.matches(c)][:limit]


if __name__ == "__main__":
    async def _d():
        src, c = HaloOglasi(), Criteria(price_max=1500)
        html = await fetch_text(src._url(c))
        cards = BeautifulSoup(html, "html.parser").select("div.product-item")
        print(f"[i] HTML {len(html)} б, карточек '.product-item': {len(cards)}")
        if not cards:
            print("[!] селектор не сработал, проверь DOM:", src._url(c)); return
        for x in src._parse(html)[:3]:
            print("-"*50); print(x.as_message(c))
    asyncio.run(_d())
