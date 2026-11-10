"""HTTP layer of the Events module. No business rules here, only translation."""
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..users.access import PermissionDenied
from .models import NewEvent
from .service import EventNotFound, EventService, EventValidationError


class EventIn(BaseModel):
    club_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    starts_at: datetime
    venue: str = Field(min_length=1)
    category: str = Field(min_length=1)
    capacity: int = Field(gt=0)


def make_router(service: EventService) -> APIRouter:
    router = APIRouter(prefix="/api/events", tags=["events"])

    @router.get("")
    def list_events():
        return service.list_events()

    @router.get("/{event_id}")
    def get_event(event_id: int):
        try:
            return service.get_event(event_id)
        except EventNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("", status_code=201)
    def create_event(body: EventIn, x_user_id: int = Header(...)):
        # Prototype simplification: the current user is sent in the X-User-Id header
        # instead of a real login.
        try:
            return service.create_event(x_user_id, NewEvent(**body.model_dump()))
        except PermissionDenied as e:
            raise HTTPException(status_code=403, detail=str(e))
        except EventValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return router
