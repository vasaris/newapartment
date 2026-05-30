from .base import Source, Listing, Criteria, DEFAULT_PRIORITY
from .fourzida import FourZida
from .cityexpert import CityExpert
from .nekretnine import Nekretnine
from .halooglasi import HaloOglasi

# Все 4 источника активны.
#   4zida      — SSR (паттерн ссылки), основной, ≈200+ кућа.
#   cityexpert — JSON-API /api/Search (ptId=2=кућа).
#   nekretnine — SSR, новый формат /izdavanje-samostalnih-kuca/ (паттерн /oglasi/).
#   halooglasi — SSR (.product-item); может блокировать дата-центры (Railway) —
#                если ловишь пустые ответы/403, закомментируй его.
SOURCES: list[Source] = [
    FourZida(),
    CityExpert(),
    Nekretnine(),
    HaloOglasi(),
]

__all__ = ["Source", "Listing", "Criteria", "DEFAULT_PRIORITY", "SOURCES",
           "FourZida", "HaloOglasi", "CityExpert", "Nekretnine"]
