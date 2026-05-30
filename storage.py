"""SQLite-хранилище (aiosqlite): критерии per-chat + дедуп виденных объявлений."""
from __future__ import annotations

import aiosqlite

from sources import Criteria, DEFAULT_PRIORITY
from config import DB_PATH

_COLS = ("region", "deal", "price_min", "price_max", "area_min",
         "plot_min", "keywords", "priority")


async def init(db_path: str = DB_PATH) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                monitoring INTEGER DEFAULT 0,
                region TEXT, deal TEXT,
                price_min INTEGER, price_max INTEGER,
                area_min INTEGER, plot_min INTEGER,
                keywords TEXT, priority TEXT
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seen (
                chat_id INTEGER, uid TEXT,
                ts DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, uid)
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                chat_id INTEGER, uid TEXT, url TEXT, title TEXT,
                price INTEGER, location TEXT,
                ts DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, uid)
            )""")
        await db.commit()


async def get_criteria(chat_id: int, db_path: str = DB_PATH) -> Criteria:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM chats WHERE chat_id=?", (chat_id,)) as cur:
            row = await cur.fetchone()
    return Criteria.from_row(dict(row)) if row else Criteria()


async def save_criteria(chat_id: int, c: Criteria, db_path: str = DB_PATH) -> None:
    d = c.to_dict()
    cols = ", ".join(_COLS)
    ph = ", ".join("?" * len(_COLS))
    upd = ", ".join(f"{c_}=excluded.{c_}" for c_ in _COLS)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"INSERT INTO chats (chat_id, {cols}) VALUES (?, {ph}) "
            f"ON CONFLICT(chat_id) DO UPDATE SET {upd}",
            (chat_id, *[d[c_] for c_ in _COLS]))
        await db.commit()


async def set_monitoring(chat_id: int, on: bool, db_path: str = DB_PATH) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO chats (chat_id, monitoring) VALUES (?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET monitoring=excluded.monitoring",
            (chat_id, 1 if on else 0))
        await db.commit()


async def monitored_chats(db_path: str = DB_PATH) -> list[int]:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT chat_id FROM chats WHERE monitoring=1") as cur:
            return [r[0] for r in await cur.fetchall()]


async def filter_new(chat_id: int, uids: list[str], db_path: str = DB_PATH) -> set[str]:
    if not uids:
        return set()
    async with aiosqlite.connect(db_path) as db:
        q = "SELECT uid FROM seen WHERE chat_id=? AND uid IN (%s)" % ",".join("?" * len(uids))
        async with db.execute(q, (chat_id, *uids)) as cur:
            known = {r[0] for r in await cur.fetchall()}
    return set(uids) - known


async def mark_seen(chat_id: int, uids: list[str], db_path: str = DB_PATH) -> None:
    if not uids:
        return
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            "INSERT OR IGNORE INTO seen (chat_id, uid) VALUES (?,?)",
            [(chat_id, u) for u in uids])
        await db.commit()


# ---------- избранное ----------
async def add_favorite(chat_id: int, uid: str, url: str, title: str,
                       price=None, location=None, db_path: str = DB_PATH) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO favorites (chat_id, uid, url, title, price, location) "
            "VALUES (?,?,?,?,?,?)",
            (chat_id, uid, url, title, price, location))
        await db.commit()


async def list_favorites(chat_id: int, db_path: str = DB_PATH) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT uid, url, title, price, location FROM favorites "
            "WHERE chat_id=? ORDER BY ts DESC", (chat_id,)) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def remove_favorite(chat_id: int, uid: str, db_path: str = DB_PATH) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM favorites WHERE chat_id=? AND uid=?", (chat_id, uid))
        await db.commit()
