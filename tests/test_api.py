import httpx
import pytest

from recipe_bot.api import BASE_URL, MealClient, RecipeServiceError


def make_client(handler):
    return MealClient(httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler)))


async def test_search_encodes_params():
    def respond(request):
        assert request.url.params["s"] == "chicken & rice"
        return httpx.Response(200, json={"meals": [{"idMeal": "123", "strMeal": "Soup"}]})

    api = make_client(respond)
    try:
        assert (await api.search("chicken & rice"))[0].name == "Soup"
    finally:
        await api.close()


async def test_null_meals_is_empty():
    api = make_client(lambda request: httpx.Response(200, json={"meals": None}))
    try:
        assert await api.search("missing") == []
        assert await api.lookup("123") is None
    finally:
        await api.close()


@pytest.mark.parametrize("payload", [{}, [], {"meals": "x"}, {"meals": [{"idMeal": "wrong"}]}])
async def test_bad_payload(payload):
    api = make_client(lambda request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(RecipeServiceError):
            await api.search("x")
    finally:
        await api.close()


async def test_retry_once_then_success():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200, json={"meals": None})

    api = make_client(respond)
    try:
        assert await api.search("x") == []
        assert len(calls) == 2
    finally:
        await api.close()


async def test_timeout_is_bounded():
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("timeout", request=request)

    api = make_client(timeout)
    try:
        with pytest.raises(RecipeServiceError):
            await api.search("x")
        assert len(calls) == 2
    finally:
        await api.close()


@pytest.mark.parametrize("status", [400, 403, 429, 500])
async def test_http_failure(status):
    api = make_client(lambda request: httpx.Response(status))
    try:
        with pytest.raises(RecipeServiceError):
            await api.search("x")
    finally:
        await api.close()
