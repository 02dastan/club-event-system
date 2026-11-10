"""HTTP layer of the Notifications module (used by the demo page)."""
from fastapi import APIRouter

from .dispatcher import NotificationDispatcher
from .outbox import SqliteOutbox


def make_router(outbox: SqliteOutbox, dispatcher: NotificationDispatcher) -> APIRouter:
    router = APIRouter(prefix="/api/notifications", tags=["notifications"])

    @router.get("")
    def list_outbox():
        return outbox.list_all()

    @router.post("/dispatch")
    def dispatch():
        return dispatcher.dispatch_pending()

    return router
