"""LanguageMiddleware resolves data['lang'] from (in priority) the saved
User.language, else the Telegram client language_code, else the default."""

from types import SimpleNamespace

from app.middlewares.language import LanguageMiddleware


async def _run(services, user):
    mw = LanguageMiddleware()
    captured = {}

    async def handler(event, data):
        captured["lang"] = data.get("lang")
        return "ok"

    data = {"event_from_user": user, "services": services}
    await mw(handler, event=SimpleNamespace(), data=data)
    return captured["lang"]


async def test_saved_language_wins(services, session):
    await services.users.set_language(555, "en")
    await session.commit()
    user = SimpleNamespace(id=555, language_code="ru")
    assert await _run(services, user) == "en"


async def test_falls_back_to_client_language(services):
    # no saved user → use the Telegram client's language_code
    user = SimpleNamespace(id=777, language_code="en")
    assert await _run(services, user) == "en"


async def test_unsupported_client_language_defaults(services):
    user = SimpleNamespace(id=888, language_code="fr")
    assert await _run(services, user) == "ru"


async def test_no_user_defaults(services):
    mw = LanguageMiddleware()
    captured = {}

    async def handler(event, data):
        captured["lang"] = data.get("lang")

    await mw(handler, event=SimpleNamespace(), data={"services": services})
    assert captured["lang"] == "ru"
