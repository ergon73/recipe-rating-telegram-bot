from dataclasses import replace

import pytest

from recipe_bot.storage import Favorites


def test_roundtrip_and_restart(store, recipe):
    store.save(11, recipe, 5)
    fresh = Favorites(store.path)
    assert fresh.get(11, recipe.id) == (recipe, 5)


def test_isolation(store, recipe):
    store.save(11, recipe, 5)
    assert store.get(12, recipe.id) is None
    assert store.list(12) == []
    assert not store.delete(12, recipe.id)
    assert store.get(11, recipe.id) == (recipe, 5)


def test_rating_upsert_and_sort(store, recipe):
    other = replace(recipe, id="52773", name="Apple")
    store.save(11, recipe, 1)
    store.save(11, other, 4)
    assert store.list(11)[0][0] == other
    store.save(11, recipe, 5)
    assert store.list(11) == [(recipe, 5), (other, 4)]
    store.save(11, recipe, 4)
    assert store.list(11) == [(other, 4), (recipe, 4)]


@pytest.mark.parametrize("rating", [-1, 0, 6, 1.5, "5", True, None])
def test_reject_invalid_rating(store, recipe, rating):
    with pytest.raises(ValueError):
        store.save(11, recipe, rating)
    assert store.list(11) == []


def test_delete_idempotent(store, recipe):
    store.save(11, recipe, 5)
    assert store.delete(11, recipe.id)
    assert not store.delete(11, recipe.id)
    assert store.list(11) == []


def test_snapshot_survives_offline(store, recipe):
    store.save(11, recipe, 4)
    assert store.get(11, recipe.id)[0].instructions == recipe.instructions


def test_bounded_favorites(store, recipe):
    for i in range(500):
        store.save(11, replace(recipe, id=str(i)), 1)
    with pytest.raises(ValueError, match="limit"):
        store.save(11, recipe, 1)
    store.save(11, replace(recipe, id="0"), 5)
    assert len(store.list(11)) == 500
