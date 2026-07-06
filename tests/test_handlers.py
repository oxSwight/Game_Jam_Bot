"""Command-level tests: drive the aiogram handlers with a fake Message that
records what the bot would send, exercising arg parsing + happy/error paths."""

from types import SimpleNamespace

from app.handlers import admin_extra
from app.models.application import ApplicationStatus
from tests.conftest import make_payload


class FakeMessage:
    def __init__(self, text: str = "", user_id: int = 111):
        self.text = text
        self.html_text = text
        self.from_user = SimpleNamespace(id=user_id, username="admin", language_code="ru")
        self.chat = SimpleNamespace(id=user_id)
        self.answers: list[str] = []
        self.documents: list[tuple] = []

    async def answer(self, text, **kw):
        self.answers.append(text)

    async def answer_document(self, document, caption=None, **kw):
        self.documents.append((document, caption))


async def _submit_approved(services, session, n):
    for i in range(n):
        read = await services.applications.submit_registration(
            make_payload(telegram_id=500 + i, nickname=f"Play{i}", email=f"h{i}@x.com")
        )
        await services.applications.update_status(read.id, ApplicationStatus.APPROVED)
    await session.commit()


# ------------------------------ /stats ------------------------------ #
async def test_cmd_stats_reports_counts(services, session):
    await _submit_approved(services, session, 2)
    msg = FakeMessage("/stats")
    await admin_extra.cmd_stats(msg, services)
    assert msg.answers
    assert "Статистика" in msg.answers[0]
    assert "Одобрено" in msg.answers[0]


# ------------------------------ /export ------------------------------ #
async def test_cmd_export_empty(services):
    msg = FakeMessage("/export")
    await admin_extra.cmd_export(msg, services)
    assert "нечего" in msg.answers[0].lower()


async def test_cmd_export_produces_csv(services, session):
    await _submit_approved(services, session, 1)
    msg = FakeMessage("/export")
    await admin_extra.cmd_export(msg, services)
    assert len(msg.documents) == 1
    document, caption = msg.documents[0]
    assert "1" in caption
    assert document.filename == "applications.csv"


async def test_cmd_export_neutralises_formula_injection(services, session):
    # A nickname that is a spreadsheet formula must not stay live in the export.
    await services.applications.submit_registration(
        make_payload(telegram_id=700, nickname="=1+1", email="evil@x.com")
    )
    await session.commit()

    msg = FakeMessage("/export")
    await admin_extra.cmd_export(msg, services)
    csv_text = msg.documents[0][0].data.decode("utf-8")

    assert "'=1+1" in csv_text            # neutralised: leading quote → inert text
    assert ",=1+1" not in csv_text        # the bare formula must not appear as a cell
