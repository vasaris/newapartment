"""Источник: 4zida.rs — основной, проверен на живой вёрстке (SSR, Next.js).

Самая большая база (≈200+ кућа за издавање в НС). Контент есть в сыром HTML,
браузер не нужен.

Ключевой приём (надёжнее любых CSS-классов): объявление — это ссылка вида
    /izdavanje-kuca/{локация-slug}/{тип}/{24-hex-id}
например /izdavanje-kuca/sirine-petrovaradin-gradske-lokacije-novi-sad/dvoetazna/6a0b3d1b65ba0aacc2044f6d
ЛОКАЦИЯ зашита прямо в slug → берём её оттуда (Petrovaradin, Sremska Kamenica…),
цену и число комнат — регуляркой из текста карточки.

Дебаг:  python -m sources.fourzida
"""
from __future__ import annotations

import re
import asyncio
from bs4 import BeautifulSoup

from .base import Source, Listing, Criteria, fetch_text, to_int

BASE = "https://www.4zida.rs"
# ссылка на объявление: .../{slug}/{tip}/{24-hex-id}
LISTING_RE = re.compile(r"/izdavanje-kuca/([^/\s\"']+)/[^/\s\"']+/([0-9a-f]{24})")
PRICE_RE = re.compile(r"([\d][\d.]*)\s*€")
ROOMS_RE = re.compile(r"([\d]+(?:[.,]\d+)?)\s*sob")
AREA_RE = re.compile(r"([\d][\d.]*)\s*m2", re.I)
# «Površina dvorišta: 2.5 a» → ари (1 ar = 100 m²)
PLOT_RE = re.compile(r"dvori[šs]ta:\s*([\d.,]+)\s*a", re.I)


def _card_text(anchor) -> str:
    """Текст карточки объявления: поднимаемся к ближайшему предку, где есть
    строка фич с 'Ažurirano' (она содержит «• Dozvoljeni ljubimci • …»)."""
    node = anchor
    for _ in range(6):
        node = node.parent
        if node is None:
            break
        txt = node.get_text(" ", strip=True)
        if "Ažurirano" in txt or "Ažurirano".lower() in txt.lower():
            if len(txt) < 700:        # защита от слишком крупного предка
                return txt
    return ""


class FourZida(Source):
    name = "4zida"

    def _url(self, c: Criteria, page: int = 1) -> str:
        url = f"{BASE}/{c.deal}/{c.region}"
        p = [f"strana={page}", "sortiranje=najnoviji"]
        if c.price_max:
            p.append(f"jeftinije_od={c.price_max}eur")
        if c.price_min:
            p.append(f"skuplje_od={c.price_min}eur")
        if c.area_min:
            p.append(f"vece_od={c.area_min}m2")
        return url + "?" + "&".join(p)

    def _parse(self, html: str) -> list[Listing]:
        soup = BeautifulSoup(html, "html.parser")
        # группируем все ссылки объявлений по id; храним текст и один anchor
        groups: dict[str, dict] = {}
        for a in soup.find_all("a", href=True):
            m = LISTING_RE.search(a["href"])
            if not m:
                continue
            slug, ext_id = m.group(1), m.group(2)
            g = groups.setdefault(ext_id, {"slug": slug, "href": a["href"],
                                           "text": "", "anchor": a})
            g["text"] += " " + a.get_text(" ", strip=True)

        out = []
        for ext_id, g in groups.items():
            href = g["href"]
            url = href if href.startswith("http") else BASE + href
            loc = g["slug"].replace("-", " ")
            text = g["text"]
            price_m = PRICE_RE.search(text)
            rooms_m = ROOMS_RE.search(text)
            area_m = AREA_RE.search(text)
            head = g["slug"].split("-")[0].replace("_", " ").title()
            # фичи из карточки: питомцы, двор, площадь плаца
            card = _card_text(g["anchor"]).lower()
            pets = "ljubimci" in card
            plot_m = PLOT_RE.search(card)
            plot = int(round(float(plot_m.group(1).replace(",", ".")) * 100)) if plot_m else None
            yard = bool(plot) or "dvoriš" in card or "dvoriš" in loc
            out.append(Listing(
                source=self.name, ext_id=ext_id,
                title=f"Kuća — {head}",
                url=url,
                price=to_int(price_m.group(1)) if price_m else None,
                area_m2=to_int(area_m.group(1)) if area_m else None,
                plot_m2=plot,
                rooms=(rooms_m.group(1) + " sobe") if rooms_m else None,
                location=loc,
                has_yard=True if yard else None,
                pets_ok=True if pets else None,
            ))
        return out

    async def search(self, c: Criteria, limit: int = 40) -> list[Listing]:
        res, seen, page = [], set(), 1
        while len(res) < limit and page <= 6:
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
        src, c = FourZida(), Criteria(price_max=2000)
        url = src._url(c)
        print("[i] URL:", url)
        html = await fetch_text(url)
        items = src._parse(html)
        print(f"[i] HTML {len(html)} б, объявлений распознано: {len(items)}")
        if not items:
            print("[!] паттерн ссылки не сматчился — проверь LISTING_RE на живой странице")
            return
        for x in sorted(items, key=lambda z: c.rank(z.location))[:5]:
            print("-" * 50); print(x.as_message(c))
    asyncio.run(_d())
