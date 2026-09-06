from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from recipe_bot.app import RecipeBot
from recipe_bot.models import Recipe
from recipe_bot.storage import Favorites


@pytest.fixture
def recipe():
    return Recipe(
        "52772",
        "Teriyaki Chicken Casserole",
        "Cook until ready.",
        ("Chicken — 500g",),
        "https://www.themealdb.com/images/media/meals/test.jpg",
        "https://www.youtube.com/watch?v=test",
        "https://example.org/recipe",
    )


@pytest.fixture
def store(tmp_path):
    return Favorites(tmp_path / "data" / "test.sqlite3")


@pytest.fixture
def api(recipe):
    api = AsyncMock()
    api.search.return_value = [recipe]
    return api


@pytest.fixture
def controller(api, store):
    return RecipeBot(api, store)


@pytest.fixture
def context():
    return SimpleNamespace(user_data={})


@pytest.fixture
def update():
    message = SimpleNamespace(
        text="chicken",
        reply_text=AsyncMock(),
        reply_photo=AsyncMock(),
    )
    query = SimpleNamespace(
        data="new",
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    return SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=11),
        effective_chat=SimpleNamespace(type="private"),
        callback_query=query,
    )
