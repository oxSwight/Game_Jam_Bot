import logging

from aiogram import Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message

from app.data.layers import LAYER_COLUMNS, LAYER_NAMES
from app.models.application import ApplicationStatus
from app.services import ServiceContainer
from app.utils.html import safe

logger = logging.getLogger(__name__)


class IsAdminFilter(BaseFilter):
    """Passes only when AdminMiddleware has stamped is_admin=True on the event data."""

    async def __call__(self, message: Message, is_admin: bool = False) -> bool:
        return is_admin


router = Router()
router.message.filter(IsAdminFilter())


@router.message(Command("pending"))
async def cmd_pending(message: Message, services: ServiceContainer) -> None:
    count = await services.applications.count_pending()
    await message.answer(f"Заявок на проверке: <b>{count}</b>")


@router.message(Command("approve"))
async def cmd_approve(message: Message, services: ServiceContainer) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /approve <id_prefix>")
        return

    prefix = parts[1]
    application = await services.applications.find_by_prefix(prefix)
    if not application:
        await message.answer("Заявка не найдена.")
        return

    await services.applications.update_status(
        application.id,
        ApplicationStatus.APPROVED,
        actor_telegram_id=message.from_user.id,
    )

    nickname = application.user.nickname if application.user else "—"
    await message.answer(f"✅ Игрок <b>{safe(nickname or '—')}</b> одобрен.")

    if services.notifications and application.user:
        await services.notifications.notify_user_approved(
            application.user.telegram_id, nickname or "—"
        )


@router.message(Command("reject"))
async def cmd_reject(message: Message, services: ServiceContainer) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /reject <id_prefix>")
        return

    prefix = parts[1]
    application = await services.applications.find_by_prefix(prefix)
    if not application:
        await message.answer("Заявка не найдена.")
        return

    nickname = application.user.nickname if application.user else "—"
    await services.applications.update_status(
        application.id,
        ApplicationStatus.REJECTED,
        actor_telegram_id=message.from_user.id,
    )
    await message.answer(f"❌ Заявка <b>{safe(nickname or '—')}</b> отклонена.")

    if services.notifications and application.user:
        await services.notifications.notify_user_rejected(application.user.telegram_id)


@router.message(Command("setlayer"))
async def cmd_set_layer(message: Message, services: ServiceContainer) -> None:
    parts = (message.text or "").split()
    if len(parts) < 4:
        layers_text = "\n".join(f"  {k}: {v}" for k, v in LAYER_NAMES.items())
        await message.answer(
            "Использование: /setlayer &lt;id_prefix&gt; &lt;1-5&gt; &lt;score&gt;\n\n"
            f"<b>Слои:</b>\n{layers_text}"
        )
        return

    prefix, layer_str, score_str = parts[1], parts[2], parts[3]

    try:
        layer = int(layer_str)
        score = float(score_str)
    except ValueError:
        await message.answer("Некорректные layer или score. Пример: /setlayer abc123 1 85.5")
        return

    if layer not in LAYER_COLUMNS:
        await message.answer("Layer должен быть от 1 до 5.")
        return

    if not (0.0 <= score <= 100.0):
        await message.answer(
            f"Недопустимый score <b>{score}</b>. Значение должно быть от 0.0 до 100.0."
        )
        return

    application = await services.applications.find_by_prefix(prefix)
    if not application:
        await message.answer("Заявка не найдена.")
        return

    updated = await services.applications.set_layer_score(
        application.id,
        layer,
        score,
        actor_telegram_id=message.from_user.id,
    )
    if not updated:
        await message.answer("Не удалось обновить score.")
        return

    nickname = application.user.nickname if application.user else "—"
    await message.answer(
        f"Layer {layer} (<i>{safe(LAYER_NAMES[layer])}</i>) = <b>{score}</b> "
        f"для <b>{safe(nickname or '—')}</b>"
    )
