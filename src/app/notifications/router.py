"""HTTP layer for notification preferences and the prototype outbox panel."""
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Response

from ..users.contacts import UserDirectory
from .dispatcher import NotificationDispatcher
from .outbox import SqliteOutbox
from .telegram import TelegramLinkService


def make_router(outbox: SqliteOutbox, dispatcher: NotificationDispatcher, *,
                current_user_id: Optional[Callable[..., int]] = None, demo_mode: bool = True,
                telegram_links: Optional[TelegramLinkService] = None,
                contacts: Optional[UserDirectory] = None) -> APIRouter:
    router = APIRouter(prefix="/api/notifications", tags=["notifications"])

    if demo_mode:
        @router.get("")
        def list_outbox():
            return outbox.list_all()

        @router.post("/dispatch")
        def dispatch():
            return dispatcher.dispatch_pending()

    if current_user_id is not None:
        @router.get("/telegram")
        def telegram_status(user_id: int = Depends(current_user_id)):
            contact = contacts.contact_for(user_id) if contacts else None
            return {"enabled": telegram_links is not None,
                    "linked": contact is not None and contact.channel == "telegram"}

        @router.post("/telegram/link")
        def issue_telegram_link(response: Response, user_id: int = Depends(current_user_id)):
            if telegram_links is None:
                raise HTTPException(503, "Telegram linking is not configured.")
            response.headers["Cache-Control"] = "no-store"
            return {"url": telegram_links.issue_link(user_id), "expires_in": telegram_links.EXPIRES_IN}

        @router.delete("/telegram/link", status_code=204)
        def unlink_telegram(user_id: int = Depends(current_user_id)):
            if telegram_links is None:
                raise HTTPException(503, "Telegram linking is not configured.")
            telegram_links.unlink(user_id)
            return Response(status_code=204)

    return router
