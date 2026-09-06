"""Bounded, asynchronous TheMealDB client. No tokens, queries or bodies in logs."""

import asyncio

import httpx

from recipe_bot.models import Recipe

BASE_URL = "https://www.themealdb.com/api/json/v1/1/"


class RecipeServiceError(Exception):
    """The service is temporarily unavailable or returned invalid data."""


class MealClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(10, connect=5),
            limits=httpx.Limits(max_connections=4),
            follow_redirects=False,
        )

    async def close(self):
        await self.client.aclose()

    async def _get(self, endpoint: str, params: dict) -> list[Recipe]:
        for attempt in range(2):
            try:
                response = await self.client.get(endpoint, params=params)
                if response.status_code >= 500 and attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or "meals" not in payload:
                    raise ValueError("Invalid payload")
                meals = payload["meals"]
                if meals is None:
                    return []
                if (
                    not isinstance(meals, list)
                    or len(meals) > 1000
                    or not all(isinstance(item, dict) for item in meals)
                ):
                    raise ValueError("Invalid meals")
                return [Recipe.from_api(item) for item in meals]
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                raise RecipeServiceError("Recipe service unavailable") from exc
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise RecipeServiceError("Invalid recipe service response") from exc
        raise RecipeServiceError("Recipe service unavailable")

    async def search(self, query: str) -> list[Recipe]:
        return await self._get("search.php", {"s": query})

    async def lookup(self, recipe_id: str) -> Recipe | None:
        recipes = await self._get("lookup.php", {"i": recipe_id})
        return recipes[0] if recipes else None
