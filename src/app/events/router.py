"""HTTP layer of the Events module. No business rules here, only translation."""
from contextlib import contextmanager
from datetime import date, datetime
from typing import Annotated, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..users.access import PermissionDenied
from .models import NewEvent
from .service import EventConflict, EventNotFound, EventService, EventValidationError


class EventIn(BaseModel):
    club_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    starts_at: datetime
    venue: str = Field(min_length=1)
    category: str = Field(min_length=1)
    capacity: int = Field(gt=0)


@contextmanager
def translate_errors():
    try:
        yield
    except EventNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except EventValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except EventConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except PermissionDenied as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


def make_router(service: EventService, current_user_id: Callable[..., int]) -> APIRouter:
    router = APIRouter(prefix="/api/events", tags=["events"])
    actor = Depends(current_user_id)

    @router.get("")
    def list_events(
        q: Annotated[str, Query(max_length=200)] = "",
        category: Optional[str] = None,
        on_date: Annotated[Optional[date], Query(alias="date")] = None,
        club_id: Annotated[Optional[int], Query(gt=0)] = None,
        limit: Annotated[Optional[int], Query(ge=1, le=200)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return service.list_events(q=q, category=category, on_date=on_date,
                                   club_id=club_id, limit=limit, offset=offset)

    @router.get("/categories")
    def categories():
        return service.categories()

    @router.get("/{event_id}")
    def get_event(event_id: int):
        with translate_errors():
            return service.get_event(event_id)

    @router.post("", status_code=201)
    def create_event(body: EventIn, user_id: int = actor):
        with translate_errors():
            return service.create_event(user_id, NewEvent(**body.model_dump()))

    @router.put("/{event_id}")
    def update_event(event_id: int, body: EventIn, user_id: int = actor):
        with translate_errors():
            return service.update_event(user_id, event_id, NewEvent(**body.model_dump()))

    @router.delete("/{event_id}")
    def cancel_event(event_id: int, user_id: int = actor):
        with translate_errors():
            return service.cancel_event(user_id, event_id)

    return router
