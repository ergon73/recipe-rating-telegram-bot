"""Atomic SQLite storage: owner-scoped reads/writes and offline recipe snapshots."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from recipe_bot.models import Recipe


class Favorites:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    user_id INTEGER NOT NULL, recipe_id TEXT NOT NULL,
                    name TEXT NOT NULL, rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                    snapshot TEXT NOT NULL, PRIMARY KEY(user_id, recipe_id)
                )
            """)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def save(self, user_id: int, recipe: Recipe, rating: int):
        if type(rating) is not int or not 1 <= rating <= 5:
            raise ValueError("Rating must be 1..5")
        with closing(self._connect()) as conn, conn:
            existing = conn.execute(
                "SELECT 1 FROM favorites WHERE user_id=? AND recipe_id=?", (user_id, recipe.id)
            ).fetchone()
            count = conn.execute(
                "SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,)
            ).fetchone()[0]
            if not existing and count >= 500:
                raise ValueError("Favorites limit reached (500)")
            conn.execute(
                """
                INSERT INTO favorites(user_id,recipe_id,name,rating,snapshot) VALUES(?,?,?,?,?)
                ON CONFLICT(user_id,recipe_id) DO UPDATE SET
                    name=excluded.name,rating=excluded.rating,snapshot=excluded.snapshot
            """,
                (
                    user_id,
                    recipe.id,
                    recipe.name,
                    rating,
                    json.dumps(recipe.to_dict(), ensure_ascii=False),
                ),
            )

    def list(self, user_id: int) -> list[tuple[Recipe, int]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT snapshot,rating FROM favorites WHERE user_id=?
                ORDER BY rating DESC,name COLLATE NOCASE ASC,recipe_id ASC
            """,
                (user_id,),
            ).fetchall()
        return [(self._recipe(row[0]), row[1]) for row in rows]

    @staticmethod
    def _recipe(raw: str) -> Recipe:
        data = json.loads(raw)
        data["ingredients"] = tuple(data["ingredients"])
        return Recipe(**data)

    def get(self, user_id: int, recipe_id: str) -> tuple[Recipe, int] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT snapshot,rating FROM favorites WHERE user_id=? AND recipe_id=?",
                (user_id, recipe_id),
            ).fetchone()
        return (self._recipe(row[0]), row[1]) if row else None

    def delete(self, user_id: int, recipe_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            return (
                conn.execute(
                    "DELETE FROM favorites WHERE user_id=? AND recipe_id=?", (user_id, recipe_id)
                ).rowcount
                > 0
            )
