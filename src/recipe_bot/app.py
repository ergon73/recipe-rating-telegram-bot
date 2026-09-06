"""Telegram transport and lifecycle. User text is searched from every menu state."""

import argparse
import logging
import os
import re
import secrets
import sqlite3
from pathlib import Path

from dotenv import dotenv_values
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from recipe_bot.api import MealClient, RecipeServiceError
from recipe_bot.models import Recipe
from recipe_bot.storage import Favorites
from recipe_bot.views import (
    FAVORITES,
    MENU,
    SEARCH,
    favorites_view,
    recipe_chunks,
    recipe_keyboard,
    search_view,
)

ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)
PROMPT = (
    "🔍 Напишите название блюда на английском, например: chicken, pasta или Arrabiata.\n"
    "TheMealDB ищет по названиям, а не переводит запросы. "
    "После поиска выберите рецепт и оцените его."
)


class SecretFilter(logging.Filter):
    """Last-line defence against Bot API URLs appearing in third-party logs."""

    def filter(self, record):
        record.msg = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{20,}", "[REDACTED]", record.getMessage())
        record.args = ()
        # Exception objects may carry credential-bearing request URLs.
        record.exc_info = None
        record.exc_text = None
        return True


class RecipeBot:
    def __init__(self, api: MealClient, favorites: Favorites, allowed: set[int] | None = None):
        self.api = api
        self.favorites = favorites
        self.allowed = allowed or set()

    async def access(self, update: Update) -> bool:
        user, chat = update.effective_user, update.effective_chat
        if not user or not chat or chat.type != "private":
            if update.callback_query:
                await update.callback_query.answer("Откройте личный чат с ботом.")
            return False
        if self.allowed and user.id not in self.allowed:
            if update.callback_query:
                await update.callback_query.answer("Бот доступен только участникам демонстрации.")
            else:
                await update.effective_message.reply_text(
                    "Бот сейчас доступен только участникам демонстрации."
                )
            return False
        return True

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.access(update):
            return
        context.user_data.clear()
        await update.effective_message.reply_text(
            "🍽 Рецепты и избранное\n\n"
            "Найдите блюдо → откройте рецепт → поставьте 1–5 ⭐.\n"
            "Оценка сохраняет рецепт в ваше личное избранное. Её можно менять.\n\n" + PROMPT,
            reply_markup=MENU,
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self.access(update):
            await update.effective_message.reply_text(
                "📖 Как пользоваться\n\n"
                "/start — главное меню\n/search — новый поиск\n"
                "/favorites — избранное\n/cancel — сброс текущего поиска\n"
                "/privacy — хранение данных\n\n"
                "Можно сразу написать название блюда. Оценка 1–5 ⭐ добавляет его "
                "в избранное; повторная оценка заменяет прежнюю. Удаление — с подтверждением.\n"
                "После перезапуска избранное сохраняется, а старый поиск нужно повторить.\n"
                "Рецепты и инструкции — на языке TheMealDB, преимущественно английском.\n"
                "Автоматического перевода нет. Бесплатный API иногда недоступен — "
                "сохранённые рецепты можно открыть без него.",
                reply_markup=MENU,
            )

    async def privacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self.access(update):
            await update.effective_message.reply_text(
                "🔒 Данные\n\n"
                "Локально в SQLite сохраняются ваш Telegram ID, избранные рецепты и оценки. "
                "Имя, телефон и история переписки не сохраняются. "
                "Поиск временно хранится в памяти до нового поиска или перезапуска.\n"
                "Текст поискового запроса передаётся TheMealDB; Telegram обрабатывает "
                "сообщения и загружает изображения. Кнопки видео и источника открывают "
                "внешние сайты.\n"
                "Удалить запись можно в избранном. Локальные резервные копии базы, "
                "если их сделал владелец бота, удаляются отдельно владельцем.",
                reply_markup=MENU,
            )

    async def prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self.access(update):
            context.user_data.pop("search", None)
            context.user_data.pop("pending_delete", None)
            await update.effective_message.reply_text(PROMPT, reply_markup=MENU)

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self.access(update):
            context.user_data.clear()
            await update.effective_message.reply_text(
                "Текущий поиск сброшен. Избранное сохранено.", reply_markup=MENU
            )

    async def show_favorites(self, update, context, page=0):
        items = self.favorites.list(update.effective_user.id)
        text, markup = favorites_view(items, page)
        await update.effective_message.reply_text(text, reply_markup=markup)

    async def favorites_command(self, update, context):
        if await self.access(update):
            await self.show_favorites(update, context)

    async def text(self, update, context):
        if not await self.access(update):
            return
        text = (update.effective_message.text or "").strip()
        if text == FAVORITES:
            await self.show_favorites(update, context)
            return
        if text == SEARCH:
            await self.prompt(update, context)
            return
        if not text or len(text) > 80:
            await update.effective_message.reply_text(
                "Введите название длиной от 1 до 80 символов.", reply_markup=MENU
            )
            return
        if re.search("[а-яА-ЯёЁ]", text):
            await update.effective_message.reply_text(
                "TheMealDB не переводит русский текст. Попробуйте английское название: "
                "chicken, pasta, soup. Русский интерфейс бота при этом сохраняется.",
                reply_markup=MENU,
            )
            return
        # Every ordinary text is a new search: no fragile ConversationHandler transitions.
        context.user_data.pop("search", None)
        context.user_data.pop("pending_delete", None)
        await update.effective_message.reply_text("🔎 Ищу рецепты…")
        try:
            recipes = await self.api.search(text)
        except RecipeServiceError:
            await update.effective_message.reply_text(
                "Сервис рецептов временно недоступен. Попробуйте позже. "
                "Ваше избранное сохранено и доступно.",
                reply_markup=MENU,
            )
            return
        if not recipes:
            await update.effective_message.reply_text(
                "Ничего не найдено. Попробуйте chicken, pasta или другое английское название.",
                reply_markup=MENU,
            )
            return
        session = secrets.token_hex(4)
        context.user_data["search"] = {"id": session, "recipes": recipes, "page": 0}
        text, markup = search_view(recipes, 0, session)
        await update.effective_message.reply_text(text, reply_markup=markup)

    def cached_recipe(self, context, user_id, recipe_id) -> Recipe | None:
        saved = self.favorites.get(user_id, recipe_id)
        if saved:
            return saved[0]
        search = context.user_data.get("search", {})
        return next((r for r in search.get("recipes", []) if r.id == recipe_id), None)

    async def show_recipe(self, update, recipe: Recipe, rating: int | None = None):
        if recipe.photo:
            try:
                await update.effective_message.reply_photo(recipe.photo, caption=recipe.name[:200])
            except TelegramError as exc:
                logger.warning("Recipe photo unavailable: %s", type(exc).__name__)
                # Recipe and controls must remain usable even if the photo server fails.
        chunks = recipe_chunks(recipe)
        for index, chunk in enumerate(chunks):
            await update.effective_message.reply_text(
                chunk,
                reply_markup=recipe_keyboard(recipe, rating) if index == len(chunks) - 1 else None,
            )

    async def stale(self, update):
        await update.effective_message.reply_text(
            "Эта кнопка относится к старому поиску или версии бота. "
            "Повторите поиск или откройте избранное.",
            reply_markup=MENU,
        )

    async def callback(self, update, context):
        if not await self.access(update):
            return
        query = update.callback_query
        # Always acknowledge before disk/network work; no forever-spinning buttons.
        await query.answer()
        data = query.data or ""
        if not isinstance(data, str) or len(data) > 64:
            await self.stale(update)
            return
        parts = data.split(":")
        action = parts[0]
        user_id = update.effective_user.id
        try:
            if data == "new":
                await self.prompt(update, context)
            elif data == "results":
                search = context.user_data.get("search")
                if not search:
                    await self.stale(update)
                    return
                text, markup = search_view(search["recipes"], search["page"], search["id"])
                await update.effective_message.reply_text(text, reply_markup=markup)
            elif action == "fav" and len(parts) == 2 and parts[1].isdigit():
                await self.show_favorites(update, context, int(parts[1]))
            elif action in {"page", "open"} and len(parts) == 3:
                search = context.user_data.get("search")
                if not search or parts[1] != search["id"] or not parts[2].isdigit():
                    await self.stale(update)
                    return
                if action == "page":
                    page = max(0, min(int(parts[2]), (len(search["recipes"]) - 1) // 5))
                    search["page"] = page
                    text, markup = search_view(search["recipes"], page, search["id"])
                    await update.effective_message.reply_text(text, reply_markup=markup)
                else:
                    recipe = next((r for r in search["recipes"] if r.id == parts[2]), None)
                    if recipe:
                        saved = self.favorites.get(user_id, recipe.id)
                        await self.show_recipe(update, recipe, saved[1] if saved else None)
                    else:
                        await self.stale(update)
            elif action == "saved" and len(parts) == 2:
                saved = self.favorites.get(user_id, parts[1])
                if saved:
                    await self.show_recipe(update, *saved)
                else:
                    await self.stale(update)
            elif action == "rate" and len(parts) == 3 and parts[2] in {"1", "2", "3", "4", "5"}:
                recipe = self.cached_recipe(context, user_id, parts[1])
                if not recipe:
                    await self.stale(update)
                    return
                rating = int(parts[2])
                self.favorites.save(user_id, recipe, rating)
                try:
                    await query.edit_message_reply_markup(
                        reply_markup=recipe_keyboard(recipe, rating)
                    )
                except BadRequest:
                    # A repeat tap may produce "message is not modified"; saving is idempotent.
                    pass
                await update.effective_message.reply_text(
                    f"✅ {recipe.name}\nОценка: {rating} ⭐. Сохранено в избранном.\n"
                    "Нажмите другую оценку, чтобы изменить её.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("⭐ Открыть избранное", callback_data="fav:0")]]
                    ),
                )
            elif action == "delete" and len(parts) == 2:
                saved = self.favorites.get(user_id, parts[1])
                if not saved:
                    await self.stale(update)
                    return
                nonce = secrets.token_hex(4)
                context.user_data["pending_delete"] = (parts[1], nonce)
                await update.effective_message.reply_text(
                    f"Удалить «{saved[0].name}» из вашего избранного?",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "Да, удалить", callback_data=f"yes:{parts[1]}:{nonce}"
                                ),
                                InlineKeyboardButton(
                                    "Отмена", callback_data=f"no:{parts[1]}:{nonce}"
                                ),
                            ]
                        ]
                    ),
                )
            elif action in {"yes", "no"} and len(parts) == 3:
                if context.user_data.get("pending_delete") != (parts[1], parts[2]):
                    await self.stale(update)
                    return
                context.user_data.pop("pending_delete", None)
                if action == "yes":
                    removed = self.favorites.delete(user_id, parts[1])
                    await update.effective_message.reply_text(
                        "✅ Рецепт удалён." if removed else "Рецепт уже удалён."
                    )
                else:
                    await update.effective_message.reply_text("Удаление отменено.")
                await self.show_favorites(update, context)
            else:
                await self.stale(update)
        except (sqlite3.Error, ValueError) as exc:
            logger.warning("Storage/input error: %s", type(exc).__name__)
            await update.effective_message.reply_text(
                "Не удалось сохранить изменение. Попробуйте ещё раз. "
                "Избранное ограничено 500 рецептами на пользователя.",
                reply_markup=MENU,
            )

    async def error(self, update: object, context):
        logger.error("Update failed: %s", type(context.error).__name__)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "Не удалось завершить действие. Попробуйте /start или /favorites.",
                    reply_markup=MENU,
                )
            except TelegramError:
                logger.warning("Could not deliver error notice")


def load_settings(env_file: Path | None = None):
    values = {**dotenv_values(env_file or ROOT / ".env"), **os.environ}
    token = (values.get("BOT_TOKEN") or "").strip()
    if not re.fullmatch(r"\d{6,}:[A-Za-z0-9_-]{20,}", token):
        raise ValueError("Задайте корректный BOT_TOKEN в локальном .env; не публикуйте его.")
    database = Path(values.get("DATABASE_PATH") or "data/recipes.sqlite3")
    if not database.is_absolute():
        database = ROOT / database
    allowed_text = values.get("ALLOWED_USER_IDS") or ""
    try:
        allowed = {int(item.strip()) for item in allowed_text.split(",") if item.strip()}
        if any(item <= 0 for item in allowed):
            raise ValueError
    except ValueError as exc:
        raise ValueError("ALLOWED_USER_IDS: ожидаются положительные ID через запятую.") from exc
    return token, database, allowed


def build_application(token: str, database: Path, allowed: set[int]) -> Application:
    api = MealClient()
    controller = RecipeBot(api, Favorites(database), allowed)

    async def post_init(application):
        webhook = await application.bot.get_webhook_info()
        if webhook.url:
            raise ValueError("У бота активен webhook. Не отключайте его без согласования.")
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Главное меню"),
                BotCommand("search", "Найти рецепт"),
                BotCommand("favorites", "Мои избранные"),
                BotCommand("help", "Справка"),
                BotCommand("privacy", "Хранение данных"),
                BotCommand("cancel", "Сброс поиска"),
            ]
        )
        logger.info("Bot initialized; polling begins")

    async def post_shutdown(application):
        await api.close()

    application = (
        Application.builder()
        .token(token)
        .concurrent_updates(False)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    for command, handler in [
        ("start", controller.start),
        ("help", controller.help),
        ("privacy", controller.privacy),
        ("search", controller.prompt),
        ("cancel", controller.cancel),
        ("favorites", controller.favorites_command),
        ("my_favorites", controller.favorites_command),
    ]:
        application.add_handler(CommandHandler(command, handler))
    application.add_handler(CallbackQueryHandler(controller.callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, controller.text))
    application.add_error_handler(controller.error)
    return application


def main():
    parser = argparse.ArgumentParser(description="Recipe Rating Telegram Bot")
    parser.add_argument("--env-file", type=Path, help="Existing local .env (never published)")
    args = parser.parse_args()
    handler = logging.StreamHandler()
    handler.addFilter(SecretFilter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for name in ("httpx", "httpcore", "telegram"):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        token, database, allowed = load_settings(args.env_file)
        application = build_application(token, database, allowed)
        application.run_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=False,
            bootstrap_retries=0,
        )
    except (ValueError, TelegramError, sqlite3.Error) as exc:
        logger.error("Startup stopped: %s", type(exc).__name__)
        if isinstance(exc, ValueError):
            logger.error("%s", exc)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
