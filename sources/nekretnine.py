"""Источник: nekretnine.rs — РАБОТАЕТ (server-rendered, новый формат URL).

Важно: рабочий URL — НОВЫЙ формат /izdavanje-samostalnih-kuca/{region}/
(старый /stambeni-objekti/kuce/... редиректит на главную). Эта страница
SSR — объявления есть в сыром HTML.

Парсим по паттерну ссылки /oglasi/{id}/. Заголовок ссылки содержит тип,
площадь и локацию ("Samostalna porodična vila 340 m², …, Novi Telep, Novi Sad"),
цена ("€ 2.900/mesec") лежит в карточке рядом — берём ближайшим предком.

Дебаг:  python -m sources.nekretnine
"""
from __future__ import annotations

import re
import asyncio
from bs4 import BeautifulSoup

from .base import Source, Listing, Criteria, fetch_text, to_int

BASE = "https://www.nekretnine.rs"
LISTING_RE = re.compile(r"/oglasi/(\d+)/?")
PRICE_RE = re.compile(r"€\s*([\d.]+)")
AREA_RE = re.compile(r"(\d[\d.]*)\s*m[²2]")


class Nekretnine(Source):
    name = "nekretnine"

    def _url(self, c: Criteria, page: int = 1) -> str:
        # самостојеће куће за издавање (idTipologia=7); регион в slug
        url = f"{BASE}/izdavanje-samostalnih-kuca/{c.region}/"
        if page > 1:
            url += f"?strana={page}"
        return url

    @staticmethod
    def _price_near(anchor) -> int | None:
        """Цена лежит в карточке рядом со ссылкой — поднимаемся к ближайшему
        предку, в тексте которого есть '€ …', и берём её."""
        node = anchor
        for _ in range(5):
            node = node.parent
            if node is None:
                break
            m = PRICE_RE.search(node.get_text(" ", strip=True))
            if m:
                return to_int(m.group(1))
        return None

    def _parse(self, html: str) -> list[Listing]:
        soup = BeautifulSoup(html, "html.parser")
        seen, out = set(), []
        for a in soup.find_all("a", href=True):
            m = LISTING_RE.search(a["href"])
            if not m:
                continue
            ext_id = m.group(1)
            if ext_id in seen:
                continue
            title = a.get("title") or a.get_text(" ", strip=True)
            if not title:
                continue
            seen.add(ext_id)
            href = a["href"]
            url = href if href.startswith("http") else BASE + href
            area_m = AREA_RE.search(title)
            # локация — последние 1-2 сегмента заголовка (через запятую)
            segs = [s.strip() for s in title.split(",") if s.strip()]
            location = ", ".join(segs[-2:]) if len(segs) >= 2 else title
            out.append(Listing(
                source=self.name, ext_id=ext_id, title=title, url=url,
                price=self._price_near(a),
                area_m2=to_int(area_m.group(1)) if area_m else None,
                location=location,
            ))
        return out

    async def search(self, c: Criteria, limit: int = 40) -> list[Listing]:
        res, seen, page = [], set(), 1
        while len(res) < limit and page <= 4:
            try:
                html = await fetch_text(self._url(c, page))
            except Exception:
                break
            batch = [x for x in self._parse(html) if x.uid not in seen]
            if not batch:
                break
            for x in batch:
                seen.add(x.uid)
            res.extend(batch)
            page += 1
        return [x for x in res if x.matches(c)][:limit]


if __name__ == "__main__":
    async def _d():
        src, c = Nekretnine(), Criteria(price_max=5000)
        print("[i] URL:", src._url(c))
        html = await fetch_text(src._url(c))
        items = src._parse(html)
        print(f"[i] HTML {len(html)} б, объявлений: {len(items)}")
        if not items:
            print("[!] паттерн /oglasi/{id}/ не сматчился — проверь живую страницу")
            return
        for x in sorted(items, key=lambda z: c.rank(z.location))[:5]:
            print("-" * 50); print(x.as_message(c))
    asyncio.run(_d())
