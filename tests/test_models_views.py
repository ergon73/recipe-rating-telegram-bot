from dataclasses import replace

import pytest

from recipe_bot.models import Recipe, safe_url
from recipe_bot.views import favorites_view, page_slice, recipe_chunks, recipe_keyboard, search_view


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://youtube.com/x",
        "https://user:pass@youtube.com",
        "https://youtube.com.evil.test/x",
        "https://youtube.com/\nx",
        None,
        "https://[bad",
        "https://evil.test/",
    ],
)
def test_reject_unsafe_video(url):
    assert safe_url(url, {"youtube.com"}) == ""


def test_valid_url():
    assert safe_url("https://youtu.be/abc", {"youtu.be"}) == "https://youtu.be/abc"


def test_api_recipe():
    result = Recipe.from_api(
        {
            "idMeal": "123",
            "strMeal": " Soup ",
            "strInstructions": None,
            "strIngredient1": " Tomato ",
            "strMeasure1": " 2 ",
            "strIngredient2": " ",
            "strYoutube": "javascript:x",
        }
    )
    assert result.id == "123"
    assert result.ingredients == ("Tomato — 2",)
    assert result.video == ""
    assert result.instructions == ""


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"idMeal": "abc", "strMeal": "x"},
        {"idMeal": "123", "strMeal": None},
        {"idMeal": "１２３", "strMeal": "x"},
    ],
)
def test_invalid_recipe(data):
    with pytest.raises(ValueError):
        Recipe.from_api(data)


@pytest.mark.parametrize(
    ("count", "requested", "expected"),
    [
        (0, 0, 0),
        (0, 10, 0),
        (6, 1, 1),
        (6, 99, 1),
        (6, -2, 0),
        (5, 1, 0),
    ],
)
def test_page_bounds(count, requested, expected):
    items, page, pages = page_slice(list(range(count)), requested)
    assert page == expected
    assert len(items) <= 5
    assert pages >= 1


def test_long_text_and_missing_video(recipe):
    long = replace(recipe, instructions="<b> & 😀" * 2000, photo="", video="")
    parts = recipe_chunks(long)
    assert all(len(p.encode("utf-16-le")) // 2 <= 4096 for p in parts)
    assert long.instructions in "".join(parts)
    assert "видеоссылка не предоставлена" in "".join(parts)
    assert all(
        not b.url or "youtu" not in b.url
        for row in recipe_keyboard(long).inline_keyboard
        for b in row
    )


def test_keyboard_rating_and_links(recipe):
    rows = recipe_keyboard(recipe, 4).inline_keyboard
    assert len(rows[0]) == 5
    assert rows[0][3].text.startswith("✓")
    assert rows[1][0].url == recipe.video


def test_callbacks_small_and_pagination(recipe):
    recipes = [replace(recipe, id=str(100 + i), name="x" * 200) for i in range(7)]
    text, markup = search_view(recipes, 0, "abcdef12")
    assert "1/2" in text
    assert any(b.callback_data == "page:abcdef12:1" for row in markup.inline_keyboard for b in row)
    assert all(
        len(b.callback_data.encode()) <= 64
        for row in markup.inline_keyboard
        for b in row
        if b.callback_data
    )


def test_empty_favorites():
    text, markup = favorites_view([], 99)
    assert "пусто" in text
    assert markup.inline_keyboard[-1][0].callback_data == "new"


def test_favorites_stars(recipe):
    text, markup = favorites_view([(recipe, 5)], 0)
    assert markup.inline_keyboard[0][0].text.startswith("⭐⭐⭐⭐⭐")
    assert "1/1" in text
