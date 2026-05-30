from .base import Source, Listing, Criteria, DEFAULT_PRIORITY
from .fourzida import FourZida
from .halooglasi import HaloOglasi
from .cityexpert import CityExpert
from .nekretnine import Nekretnine

# Активные источники. 4zida — основной (SSR, проверен).
# halooglasi — SSR, но может блокировать запросы с дата-центра (Railway);
#   если ловишь блок — оставь только 4zida.
# cityexpert и nekretnine — SPA, нужен их JSON-API (см. докстринги),
#   поэтому по умолчанию ВЫКЛЮЧЕНЫ. Допилишь API → раскомментируй.
SOURCES: list[Source] = [
    FourZida(),
    HaloOglasi(),
    # CityExpert(),    # включить после реализации JSON-API
    # Nekretnine(),    # включить после реализации JSON-API
]

__all__ = ["Source", "Listing", "Criteria", "DEFAULT_PRIORITY", "SOURCES",
           "FourZida", "HaloOglasi", "CityExpert", "Nekretnine"]
