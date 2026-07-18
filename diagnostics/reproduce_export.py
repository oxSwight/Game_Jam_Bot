"""Прогоняет НАСТОЯЩИЙ хендлер /export (app.handlers.admin_extra.cmd_export)
по живой базе и сохраняет полученный CSV в /tmp/applications.csv.

Только чтение (list_all_with_users), в базу ничего не пишет. Запуск в контейнере:
    docker cp diagnostics/reproduce_export.py gamejam_bot-bot-1:/tmp/
    docker exec gamejam_bot-bot-1 python /tmp/reproduce_export.py
    docker cp gamejam_bot-bot-1:/tmp/applications.csv .
"""

import asyncio
from types import SimpleNamespace


class FakeMessage:
    """Как в tests/test_handlers.py: записывает то, что бот отправил бы."""

    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=0, username="repro", language_code="ru")
        self.answers: list[str] = []
        self.documents: list[tuple] = []

    async def answer(self, text, **kw):
        self.answers.append(text)

    async def answer_document(self, document, caption=None, **kw):
        self.documents.append((document, caption))


async def main() -> None:
    from app.core.database import async_session_maker
    from app.handlers import admin_extra
    from app.services import ServiceContainer

    async with async_session_maker() as session:
        services = ServiceContainer.from_session(session=session, notifications=None)
        msg = FakeMessage()
        await admin_extra.cmd_export(msg, services)

    if not msg.documents:
        print("export вернул:", msg.answers)
        return
    for document, caption in msg.documents:
        path = f"/tmp/{document.filename}"
        with open(path, "wb") as fh:
            fh.write(document.data)
        print(f"OK: {caption!r} -> {path} ({len(document.data)} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
