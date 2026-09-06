"""Pure UI construction; small messages, no raw HTML/Markdown interpolation."""

from telegram import InlineKeyboardButton as Button
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

from recipe_bot.models import Recipe

SEARCH = "🔍 Поиск рецепта"
FAVORITES = "⭐ Мои избранные"
MENU = ReplyKeyboardMarkup([[SEARCH, FAVORITES]], resize_keyboard=True, is_persistent=True)
PAGE_SIZE = 5


def page_slice(items: list, page: int):
    pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    return items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE], page, pages


def footer():
    return [
        Button("🔍 Новый поиск", callback_data="new"),
        Button("⭐ Избранное", callback_data="fav:0"),
    ]


def search_view(recipes: list[Recipe], page: int, session: str):
    items, page, pages = page_slice(recipes, page)
    rows = [[Button(r.name[:55], callback_data=f"open:{session}:{r.id}")] for r in items]
    nav = []
    if page:
        nav.append(Button("← Назад", callback_data=f"page:{session}:{page - 1}"))
    if page + 1 < pages:
        nav.append(Button("Далее →", callback_data=f"page:{session}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append(footer())
    return (
        f"🍽 Найдено: {len(recipes)} · Страница {page + 1}/{pages}\nВыберите рецепт:",
        InlineKeyboardMarkup(rows),
    )


def favorites_view(items: list[tuple[Recipe, int]], page: int):
    chunk, page, pages = page_slice(items, page)
    rows = []
    for recipe, rating in chunk:
        rows.append(
            [Button(f"{'⭐' * rating} {recipe.name[:40]}", callback_data=f"saved:{recipe.id}")]
        )
        actions = [Button("🗑 Удалить", callback_data=f"delete:{recipe.id}")]
        if recipe.video:
            actions.insert(0, Button("🎥 Видео", url=recipe.video))
        rows.append(actions)
    nav = []
    if page:
        nav.append(Button("← Назад", callback_data=f"fav:{page - 1}"))
    if page + 1 < pages:
        nav.append(Button("Далее →", callback_data=f"fav:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append(footer())
    text = (
        f"⭐ Избранное: {len(items)} · Страница {page + 1}/{pages}\n"
        "Сначала — самые высокие оценки. Нажмите рецепт, чтобы открыть или переоценить."
    )
    if not items:
        text = "⭐ Избранное пока пусто. Найдите рецепт и поставьте ему оценку."
    return text, InlineKeyboardMarkup(rows)


def recipe_keyboard(recipe: Recipe, rating: int | None = None):
    rows = [
        [
            Button(f"{'✓ ' if rating == i else ''}{i} ⭐", callback_data=f"rate:{recipe.id}:{i}")
            for i in range(1, 6)
        ]
    ]
    if recipe.video:
        rows.append([Button("🎥 Видеорецепт", url=recipe.video)])
    if recipe.source:
        rows.append([Button("🌐 Источник рецепта", url=recipe.source)])
    rows.append([Button("← Результаты поиска", callback_data="results")])
    rows.append(footer())
    return InlineKeyboardMarkup(rows)


def recipe_chunks(recipe: Recipe) -> list[str]:
    ingredients = "\n".join(f"• {item}" for item in recipe.ingredients) or "Не указаны."
    text = (
        f"🍽 {recipe.name}\n\n🥕 Ингредиенты\n{ingredients}\n\n"
        f"📝 Приготовление\n{recipe.instructions or 'Инструкция не указана.'}\n\n"
        "Источник: TheMealDB. Оригинальный язык рецепта сохранён.\n"
        + (
            "🎥 Видеорецепт — по кнопке ниже."
            if recipe.video
            else "🎥 Для этого рецепта видеоссылка не предоставлена."
        )
        + "\n\nОцените от 1 до 5 ⭐ — рецепт сохранится в избранном."
    )
    # <= 3600 UTF-16 units even for all-astral characters; preserve word boundaries.
    chunks = []
    while len(text) > 1800:
        split = text.rfind("\n", 900, 1801)
        if split == -1:
            split = text.rfind(" ", 900, 1801)
        end = split + 1 if split != -1 else 1800
        chunks.append(text[:end])
        text = text[end:]
    if text:
        chunks.append(text)
    return chunks
