"""Integration smoke tests for app wiring: routers register cleanly, the
middleware stack composes, and the i18n catalog is internally consistent. These
catch registration-time errors (bad filters, duplicate handlers) that unit
tests on individual handlers miss."""

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.core.i18n import SUPPORTED_LANGS, assert_catalog_complete, t
from app.handlers.admin import router as admin_router
from app.handlers.admin_extra import router as admin_extra_router
from app.handlers.fallback import router as fallback_router
from app.handlers.membership import router as membership_router
from app.handlers.registration import router as registration_router


def test_routers_register_without_error():
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(registration_router)
    dp.include_router(admin_router)
    dp.include_router(admin_extra_router)
    dp.include_router(membership_router)
    dp.include_router(fallback_router)  # must stay last: catch-all for stale taps
    # sub_routers reflects successful inclusion
    assert len(dp.sub_routers) == 5


def test_middlewares_compose():
    from app.middlewares import (
        AdminMiddleware,
        DbSessionMiddleware,
        LanguageMiddleware,
        ServicesMiddleware,
        ThrottlingMiddleware,
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(ThrottlingMiddleware())
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(ServicesMiddleware())
    dp.update.middleware(LanguageMiddleware())
    dp.update.middleware(AdminMiddleware())
    # registering the same stack must not raise


def test_every_status_label_localised():
    for status in ("pending_review", "approved", "rejected"):
        for lang in SUPPORTED_LANGS:
            assert t(f"status_{status}", lang) != f"status_{status}"


def test_catalog_complete():
    assert_catalog_complete()
