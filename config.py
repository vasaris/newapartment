import os

BOT_TOKEN = os.environ["BOT_TOKEN"]
POLL_MINUTES = int(os.environ.get("POLL_MINUTES", "30"))
# путь к базе. Локально — kuca.db рядом с кодом; на Railway укажи
# переменную DB_PATH=/data/kuca.db (Volume примонтирован в /data).
DB_PATH = os.environ.get("DB_PATH", "kuca.db")
