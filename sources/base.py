"""Базовые модели, общие хелперы и интерфейс источника.

Добавить портал: наследуй Source, реализуй async search(c) -> list[Listing].
Дедуп, мониторинг, ранжирование и отправка в ТГ переиспользуются.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional

import aiohttp

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_num = re.compile(r"\d[\d.\s]*")


def to_int(s: str | None) -> Optional[int]:
    """'1.250 €' / '85 m²' -> 1250 / 85."""
    if not s:
        return None
    m = _num.search(s)
    if not m:
        return None
    digits = re.sub(r"[.\s]", "", m.group())
    return int(digits) if digits else None


async def fetch_text(url: str, timeout: int = 20) -> str:
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers={"User-Agent": UA, "Accept-Language": "sr,en;q=0.8"},
                         timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            r.raise_for_status()
            return await r.text()


# Приоритет локаций по умолчанию: Нови-Сад первый, дальше ближайшие.
# Ключевые слова матчатся по тексту локации объявления (lowercase).
# Минимальная цена-за-метр: ниже — почти всегда койко-место «смештај за
# раднике», а не дом целиком. Нормальный дом — 2..15 €/m².
MIN_EUR_PER_M2 = 1.0

# Жёсткие исключения (выкидываем из выдачи целиком):
#  - этаж в доме («na 1. spratu») = неполное владение, не весь дом+двор;
#  - «pravnim licima» = сдаётся только юрлицам (бизнес-аренда);
#  - «radnike» = смештај за раднике (общага/койко-места).
# Осознанно НЕ режем по «poslovni prostor»: у нормальных домов часто пишут
# «za stanovanje ili poslovni prostor» — это опция, не категория.
import re as _re
_FLOOR_RX = _re.compile(r"\bna\s+\d+\.?\s*sprat", _re.I)
_EXCL_RX = _re.compile(r"pravnim\s+licima|\bradnik", _re.I)


def _excluded_text(t: str) -> bool:
    if not t:
        return False
    return bool(_FLOOR_RX.search(t) or _EXCL_RX.search(t))
DEFAULT_PRIORITY = [
    "novi sad", "petrovaradin", "sremska kamenica", "veternik",
    "futog", "sremski karlovci", "kać", "rumenka",
]


@dataclass
class Criteria:
    region: str = "novi-sad"          # широкий slug, запрашиваемый на портале
    deal: str = "izdavanje-kuca"      # издавање кућа
    price_min: int = 0
    price_max: int = 1000             # EUR/мес
    area_min: int = 0                 # m² жилья
    plot_min: int = 0                 # m² плаца (двора)
    keywords: list[str] = field(default_factory=list)
    priority: list[str] = field(default_factory=lambda: list(DEFAULT_PRIORITY))

    def rank(self, location_text: str | None) -> int:
        """Приоритет локации, меньше = выше. priority[0] — главный город (=0),
        остальные — тиры по порядку. Важно: у порталов в тексте локации почти
        всегда присутствует «novi sad» как град, поэтому вторичные локации
        (Петроварадин, Каменица…) проверяются ПЕРЕД главным городом —
        иначе всё схлопнулось бы в приоритет 0."""
        t = (location_text or "").lower()
        secondary = self.priority[1:] if self.priority else []
        for i, kw in enumerate(secondary):
            if kw and kw in t:
                return i + 1                 # 1, 2, 3…
        primary = self.priority[0] if self.priority else "novi sad"
        if primary in t:
            return 0                         # главный город (НС) — наверх
        return len(secondary) + 1            # неопознанная локация — в самый низ

    def to_dict(self) -> dict:
        d = asdict(self)
        d["keywords"] = ",".join(self.keywords)
        d["priority"] = ",".join(self.priority)
        return d

    @classmethod
    def from_row(cls, row: dict) -> "Criteria":
        def split(v):
            return [x for x in (v or "").split(",") if x]
        return cls(
            region=row.get("region", "novi-sad"),
            deal=row.get("deal", "izdavanje-kuca"),
            price_min=int(row.get("price_min", 0) or 0),
            price_max=int(row.get("price_max", 1000) or 1000),
            area_min=int(row.get("area_min", 0) or 0),
            plot_min=int(row.get("plot_min", 0) or 0),
            keywords=split(row.get("keywords")),
            priority=split(row.get("priority")) or list(DEFAULT_PRIORITY),
        )


@dataclass
class Listing:
    source: str
    ext_id: str
    title: str
    url: str
    price: Optional[int] = None
    area_m2: Optional[int] = None
    plot_m2: Optional[int] = None
    location: Optional[str] = None
    rooms: Optional[str] = None
    heating: Optional[str] = None
    image: Optional[str] = None
    has_yard: Optional[bool] = None   # двор/двориште подтверждён (None = неизвестно)
    pets_ok: Optional[bool] = None    # питомцы разрешены (None = неизвестно)
    desc: Optional[str] = None        # описание/мета со страницы (для фильтров)

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.ext_id}"

    def is_excluded(self) -> bool:
        """Жёстко исключаем: сдаётся этаж (не весь дом), только юрлицам,
        общага «за раднике». Текст берём из заголовка/локации/описания."""
        blob = " ".join(x for x in (self.title, self.location, self.desc) if x)
        return _excluded_text(blob)

    def dog_score(self) -> int:
        """Сколько «собачьих» сигналов подтверждено: двор + питомцы (0..2)."""
        return (1 if self.has_yard else 0) + (1 if self.pets_ok else 0)

    def matches(self, c: Criteria) -> bool:
        if self.is_excluded():
            return False
        if self.price is not None:
            if c.price_min and self.price < c.price_min:
                return False
            if c.price_max and self.price > c.price_max:
                return False
            # отсечка мусора (койко-места «смештај за раднике»): аномально
            # низкая цена-за-метр. Считаем только когда известны и цена, и площадь.
            if self.area_m2 and self.price / self.area_m2 < MIN_EUR_PER_M2:
                return False
        if c.area_min and self.area_m2 is not None and self.area_m2 < c.area_min:
            return False
        if c.plot_min and self.plot_m2 is not None and self.plot_m2 < c.plot_min:
            return False
        if c.keywords:
            hay = f"{self.title} {self.location or ''}".lower()
            if not any(k.lower() in hay for k in c.keywords):
                return False
        return True

    def as_message(self, c: "Criteria | None" = None) -> str:
        star = ""
        if c is not None and c.rank(self.location) == 0:
            star = "⭐️ "   # объявление в приоритетной локации (Нови-Сад)
        parts = [f"{star}🏡 <b>{self.title}</b>"]
        badges = []
        if self.has_yard:
            badges.append("🌳 двор")
        if self.pets_ok:
            badges.append("🐕 može pas")
        if badges:
            parts.append(" · ".join(badges))
        meta = []
        if self.price is not None:
            meta.append(f"💶 {self.price} €")
        if self.area_m2:
            meta.append(f"📐 {self.area_m2} m²")
        if self.plot_m2:
            meta.append(f"🌿 plac {self.plot_m2} m²")
        if meta:
            parts.append(" · ".join(meta))
        if self.location:
            parts.append(f"📍 {self.location}")
        if self.heating:
            parts.append(f"🔥 {self.heating}")
        parts.append(f"<i>[{self.source}]</i>")
        parts.append(f'\n<a href="{self.url}">Отворити оглас →</a>')
        return "\n".join(parts)


class Source(ABC):
    name: str = "base"

    @abstractmethod
    async def search(self, c: Criteria, limit: int = 40) -> list[Listing]:
        ...
