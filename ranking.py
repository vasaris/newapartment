"""Рейтинг объявлений по тирам S/A/B/C/D/E.

score(x, c) даёт числовую оценку по нашим критериям (двор, собака, отопление,
локация, цена/бюджет, площадь), tier() переводит её в букву. dedup() схлопывает
одинаковые объявления, в т.ч. одну и ту же кућу с разных порталов.

Веса вынесены наверх — подкручивай под себя.
"""
from __future__ import annotations

from sources import Criteria, Listing

# --- веса скоринга ---
BASE = 50.0
LOC_BONUS = {0: 22, 1: 14, 2: 10, 3: 7, 4: 5}   # по c.rank(): НС=0 → +22
LOC_UNKNOWN = -8                                  # локация вне приоритета
YARD_BONUS = 14
PETS_BONUS = 12
PLAC_PER_AR = 1.4         # за каждый ар плаца (до 10 ари)
PLAC_AR_CAP = 10
GAS_BONUS = 6             # газ/централно/подно
STRUJA_PENALTY = 9        # только электроотопление
AREA_BONUS = 3            # площадь не ниже area_min
UNDER_BUDGET_BONUS = 10   # максимум, если сильно дешевле бюджета
OVER_BUDGET_PENALTY = 28  # на единицу превышения бюджета

# порог тира: score >= cutoff
TIER_CUTOFFS = [("S", 88), ("A", 78), ("B", 68), ("C", 58), ("D", 48)]
TIERS = ["S", "A", "B", "C", "D", "E"]


def score(x: Listing, c: Criteria) -> float:
    s = BASE
    r = c.rank(x.location)
    s += LOC_BONUS.get(r, LOC_UNKNOWN if r >= 99 else 3)
    if x.has_yard:
        s += YARD_BONUS
    if x.plot_m2:
        s += min(x.plot_m2 / 100.0, PLAC_AR_CAP) * PLAC_PER_AR
    if x.pets_ok:
        s += PETS_BONUS
    blob = f"{x.heating or ''} {x.desc or ''}".lower()
    if any(k in blob for k in ("gas", "centralno", " cg", "podno", "centraln")):
        s += GAS_BONUS
    if "struja" in blob or "na struju" in blob:
        s -= STRUJA_PENALTY
    budget = c.price_max or 1300
    if x.price:
        if x.price <= budget:
            s += UNDER_BUDGET_BONUS * (1 - x.price / budget)
        else:
            s -= OVER_BUDGET_PENALTY * (x.price / budget - 1)
    if x.area_m2 and x.area_m2 >= (c.area_min or 0):
        s += AREA_BONUS
    return round(max(0.0, min(100.0, s)), 1)


def tier(s: float) -> str:
    for name, cut in TIER_CUTOFFS:
        if s >= cut:
            return name
    return "E"


# --- дедупликация (в т.ч. кросс-портальная) ---
# приоритет источника при выборе «представителя» дубля (меньше = лучше):
# cityexpert даёт структурные флаги, 4zida — плац; их держим первыми.
_SRC_PRIORITY = {"cityexpert": 0, "4zida": 1, "nekretnine": 2, "halooglasi": 3}
_LOCALITY_HINTS = ("petrovaradin", "sremska kamenica", "kamenica", "veternik",
                   "futog", "telep", "adice", "lipov gaj", "podbara", "paragovo",
                   "kovilj", "novi sad")


def _locality(loc: str | None) -> str:
    t = (loc or "").lower()
    for h in _LOCALITY_HINTS:
        if h in t:
            return h
    return t.split(",")[0].strip()[:20]


def _dedup_key(x: Listing):
    """Одинаковыми считаем объявления с той же ценой, площадью и населем —
    обычно это одна кућа, перевыложенная на разных порталах."""
    return (x.price or 0, x.area_m2 or 0, _locality(x.location))


def _completeness(x: Listing) -> int:
    return sum(v is not None for v in (x.has_yard, x.pets_ok, x.plot_m2,
                                       x.price, x.area_m2))


def dedup(listings: list[Listing]) -> list[Listing]:
    """Схлопывает дубли, оставляя самый «полный»/приоритетный экземпляр.
    Если у дублей цена/площадь известны (не 0) — группируем; объявления без
    цены И площади не группируем (мало данных, можно случайно слить разное)."""
    best: dict[tuple, Listing] = {}
    passthrough: list[Listing] = []
    for x in listings:
        if not x.price and not x.area_m2:
            passthrough.append(x)
            continue
        k = _dedup_key(x)
        cur = best.get(k)
        if cur is None:
            best[k] = x
            continue
        # выбираем лучший экземпляр: полнее данных, затем приоритет источника
        better = (_completeness(x), -_SRC_PRIORITY.get(x.source, 9)) > \
                 (_completeness(cur), -_SRC_PRIORITY.get(cur.source, 9))
        if better:
            best[k] = x
    return list(best.values()) + passthrough


def rank_all(listings: list[Listing], c: Criteria) -> list[dict]:
    """Дедуп + скоринг + тир, отсортировано: тир, затем score по убыванию."""
    uniq = dedup(listings)
    scored = []
    for x in uniq:
        sc = score(x, c)
        scored.append({"listing": x, "score": sc, "tier": tier(sc)})
    order = {t: i for i, t in enumerate(TIERS)}
    scored.sort(key=lambda d: (order[d["tier"]], -d["score"]))
    return scored
