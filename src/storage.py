from __future__ import annotations

import aiosqlite
from typing import Optional, List, Tuple
import time

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
	user_id INTEGER PRIMARY KEY,
	banned INTEGER NOT NULL DEFAULT 0,
	created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	user_id INTEGER NOT NULL,
	long_url TEXT NOT NULL,
	short_url TEXT NOT NULL,
	alias TEXT,
	created_at INTEGER NOT NULL,
	FOREIGN KEY(user_id) REFERENCES users(user_id)
);
"""


class Storage:
	def __init__(self, db_path: str = "bot.db") -> None:
		self._db_path = db_path

	async def init(self) -> None:
		async with aiosqlite.connect(self._db_path) as db:
			await db.executescript(SCHEMA)
			# Ensure users.api_key exists
			cols = []
			async with db.execute("PRAGMA table_info(users)") as cur:
				async for row in cur:
					cols.append(row[1])
			if "api_key" not in cols:
				await db.execute("ALTER TABLE users ADD COLUMN api_key TEXT")
			await db.commit()

	async def upsert_user(self, user_id: int) -> None:
		now = int(time.time())
		async with aiosqlite.connect(self._db_path) as db:
			await db.execute(
				"INSERT INTO users(user_id, banned, created_at) VALUES(?, 0, ?) ON CONFLICT(user_id) DO NOTHING",
				(user_id, now),
			)
			await db.commit()

	async def is_banned(self, user_id: int) -> bool:
		async with aiosqlite.connect(self._db_path) as db:
			async with db.execute("SELECT banned FROM users WHERE user_id=?", (user_id,)) as cur:
				row = await cur.fetchone()
				return bool(row and row[0])

	async def set_banned(self, user_id: int, banned: bool) -> None:
		now = int(time.time())
		async with aiosqlite.connect(self._db_path) as db:
			await db.execute("INSERT INTO users(user_id, banned, created_at) VALUES(?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET banned=excluded.banned", (user_id, 1 if banned else 0, now))
			await db.commit()

	async def set_user_api_key(self, user_id: int, api_key: str) -> None:
		now = int(time.time())
		async with aiosqlite.connect(self._db_path) as db:
			await db.execute(
				"INSERT INTO users(user_id, banned, created_at, api_key) VALUES(?, 0, ?, ?) ON CONFLICT(user_id) DO UPDATE SET api_key=excluded.api_key",
				(user_id, now, api_key),
			)
			await db.commit()

	async def get_user_api_key(self, user_id: int) -> Optional[str]:
		async with aiosqlite.connect(self._db_path) as db:
			async with db.execute("SELECT api_key FROM users WHERE user_id=?", (user_id,)) as cur:
				row = await cur.fetchone()
				return row[0] if row and row[0] else None

	async def record_link(self, user_id: int, long_url: str, short_url: str, alias: Optional[str]) -> None:
		now = int(time.time())
		async with aiosqlite.connect(self._db_path) as db:
			await db.execute("INSERT INTO links(user_id, long_url, short_url, alias, created_at) VALUES(?,?,?,?,?)", (user_id, long_url, short_url, alias, now))
			await db.commit()

	async def user_stats(self, user_id: int) -> Tuple[int, Optional[str]]:
		async with aiosqlite.connect(self._db_path) as db:
			async with db.execute("SELECT COUNT(*), MAX(created_at) FROM links WHERE user_id=?", (user_id,)) as cur:
				row = await cur.fetchone()
				return int(row[0] or 0), str(row[1]) if row and row[1] else None

	async def global_stats(self) -> Tuple[int, int]:
		async with aiosqlite.connect(self._db_path) as db:
			async with db.execute("SELECT COUNT(*), COUNT(DISTINCT user_id) FROM links") as cur:
				row = await cur.fetchone()
				return int(row[0] or 0), int(row[1] or 0)
