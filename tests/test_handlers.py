import sqlite3
from dataclasses import replace
from unittest.mock import patch

import pytest
from telegram.error import BadRequest

from recipe_bot.api import RecipeServiceError
from recipe_bot.views import FAVORITES, SEARCH


def replies(update):
    return "\n".join(str(c.args[0]) for c in update.effective_message.reply_text.await_args_list)


async def test_new_search_button_then_text(controller, api, update, context):
    update.callback_query.data = "new"
    await controller.callback(update, context)
    await controller.text(update, context)
    api.search.assert_awaited_once_with("chicken")
    assert "search" in context.user_data


async def test_search_button_works_from_any_state(controller, api, update, context):
    context.user_data["legacy_state"] = "MENU"
    update.effective_message.text = SEARCH
    await controller.text(update, context)
    update.effective_message.text = "pasta"
    await controller.text(update, context)
    api.search.assert_awaited_once_with("pasta")


async def test_favorites_button_no_api(controller, api, store, recipe, update, context):
    store.save(11, recipe, 4)
    update.effective_message.text = FAVORITES
    await controller.text(update, context)
    assert "Избранное: 1" in replies(update)
    api.search.assert_not_called()


async def test_empty_search(controller, api, update, context):
    api.search.return_value = []
    await controller.text(update, context)
    assert "Ничего не найдено" in replies(update)


async def test_api_failure_not_reported_as_empty(controller, api, update, context):
    api.search.side_effect = RecipeServiceError()
    await controller.text(update, context)
    assert "временно недоступен" in replies(update)
    assert "Ничего не найдено" not in replies(update)


@pytest.mark.parametrize("text", ["", "x" * 81, "курица"])
async def test_invalid_search(controller, api, update, context, text):
    update.effective_message.text = text
    await controller.text(update, context)
    api.search.assert_not_called()


async def test_stale_search_buttons(controller, update, context, recipe):
    context.user_data["search"] = {"id": "fresh", "recipes": [recipe], "page": 0}
    update.callback_query.data = "open:old:52772"
    await controller.callback(update, context)
    assert "старому поиску" in replies(update)
    update.callback_query.answer.assert_awaited_once()


async def test_search_pages_cached(controller, api, update, context, recipe):
    context.user_data["search"] = {
        "id": "fresh",
        "recipes": [replace(recipe, id=str(i)) for i in range(8)],
        "page": 0,
    }
    update.callback_query.data = "page:fresh:1"
    await controller.callback(update, context)
    assert "2/2" in replies(update)
    assert context.user_data["search"]["page"] == 1
    api.search.assert_not_called()


async def test_favorites_pagination_regression(controller, store, update, context, recipe):
    for i in range(7):
        store.save(11, replace(recipe, id=str(i)), 4)
    update.callback_query.data = "fav:1"
    await controller.callback(update, context)
    assert "2/2" in replies(update)


async def test_delete_cancel_and_confirm(controller, store, update, context, recipe):
    store.save(11, recipe, 5)
    update.callback_query.data = f"delete:{recipe.id}"
    await controller.callback(update, context)
    rid, nonce = context.user_data["pending_delete"]
    update.callback_query.data = f"no:{rid}:{nonce}"
    await controller.callback(update, context)
    assert store.get(11, rid)
    assert "Удаление отменено" in replies(update)
    assert "Избранное: 1" in replies(update)
    update.callback_query.data = f"delete:{rid}"
    await controller.callback(update, context)
    rid, nonce = context.user_data["pending_delete"]
    update.callback_query.data = f"yes:{rid}:{nonce}"
    await controller.callback(update, context)
    assert store.get(11, rid) is None
    assert "пусто" in replies(update)
    # Old confirmation cannot trigger a second delete.
    await controller.callback(update, context)
    assert "старому поиску" in replies(update)


async def test_cross_user_delete_cannot_modify(controller, store, update, context, recipe):
    store.save(12, recipe, 5)
    update.callback_query.data = f"delete:{recipe.id}"
    await controller.callback(update, context)
    assert store.get(12, recipe.id)
    assert "pending_delete" not in context.user_data


async def test_rate_and_rerate_without_network(controller, api, update, context, recipe, store):
    context.user_data["search"] = {"id": "fresh", "recipes": [recipe], "page": 0}
    for rating in (5, 2):
        update.callback_query.data = f"rate:{recipe.id}:{rating}"
        await controller.callback(update, context)
    assert store.list(11) == [(recipe, 2)]
    api.lookup.assert_not_called()
    assert update.callback_query.answer.await_count == 2


async def test_repeated_rating_is_safe(controller, update, context, recipe, store):
    store.save(11, recipe, 5)
    update.callback_query.data = f"rate:{recipe.id}:5"
    update.callback_query.edit_message_reply_markup.side_effect = BadRequest("Message not modified")
    await controller.callback(update, context)
    assert store.get(11, recipe.id)[1] == 5
    assert "Сохранено" in replies(update)


async def test_failed_storage_does_not_claim_success(controller, update, context, recipe):
    context.user_data["search"] = {"id": "fresh", "recipes": [recipe], "page": 0}
    update.callback_query.data = f"rate:{recipe.id}:5"
    with patch.object(controller.favorites, "save", side_effect=sqlite3.OperationalError):
        await controller.callback(update, context)
    assert "Не удалось сохранить" in replies(update)
    assert "✅" not in replies(update)


async def test_offline_saved_recipe_and_photo_failure(
    controller, store, api, update, context, recipe
):
    store.save(11, recipe, 5)
    update.effective_message.reply_photo.side_effect = BadRequest("photo unavailable")
    update.callback_query.data = f"saved:{recipe.id}"
    await controller.callback(update, context)
    assert recipe.instructions in replies(update)
    assert "Оцените" in replies(update)
    api.lookup.assert_not_called()


async def test_ack_before_recipe_render(controller, update, context, recipe, store):
    store.save(11, recipe, 5)
    update.callback_query.data = f"saved:{recipe.id}"

    async def photo(*args, **kwargs):
        update.callback_query.answer.assert_awaited_once()

    update.effective_message.reply_photo.side_effect = photo
    await controller.callback(update, context)


@pytest.mark.parametrize(
    "data",
    [
        "already_rated",
        "noop",
        "new_search",
        "rate:52772:6",
        "fav:-1",
        "yes:52772:forged",
        "bad",
        "x" * 65,
    ],
)
async def test_bad_or_legacy_callbacks(controller, update, context, data):
    update.callback_query.data = data
    await controller.callback(update, context)
    update.callback_query.answer.assert_awaited_once()
    assert "старому поиску" in replies(update)


async def test_private_chat_only(controller, api, update, context):
    update.effective_chat.type = "group"
    await controller.text(update, context)
    api.search.assert_not_called()


async def test_allowlist(controller, api, update, context):
    controller.allowed = {12}
    update.callback_query = None
    await controller.text(update, context)
    api.search.assert_not_called()
    assert "участникам" in replies(update)


async def test_start_cancel_preserve_database(controller, store, recipe, update, context):
    store.save(11, recipe, 3)
    context.user_data["search"] = {"id": "old"}
    await controller.start(update, context)
    assert not context.user_data
    await controller.cancel(update, context)
    assert store.get(11, recipe.id)


async def test_help_privacy_commands(controller, update, context):
    await controller.help(update, context)
    await controller.privacy(update, context)
    assert "/favorites" in replies(update)
    assert "SQLite" in replies(update)
