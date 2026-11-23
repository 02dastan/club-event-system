"""Club catalog, membership and administration API."""
from contextlib import contextmanager
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..users.access import PermissionDenied
from .service import ClubNotFound, ClubService, ClubValidationError


class ClubIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    organizer_id: int = Field(gt=0)


@contextmanager
def translate_errors():
    try:
        yield
    except ClubNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ClubValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except PermissionDenied as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


def make_router(service: ClubService, current_user_id: Callable[..., int]) -> APIRouter:
    router = APIRouter(prefix="/api/clubs", tags=["clubs"])
    actor = Depends(current_user_id)

    @router.get("")
    def list_clubs():
        return service.list_clubs()

    @router.get("/memberships")
    def list_memberships(user_id: int = actor):
        return service.memberships_for(user_id)

    @router.get("/{club_id}")
    def get_club(club_id: int):
        with translate_errors():
            return service.get_club(club_id)

    @router.put("/{club_id}/membership", status_code=204, response_class=Response)
    def join_club(club_id: int, user_id: int = actor):
        with translate_errors():
            service.join_club(user_id, club_id)

    @router.delete("/{club_id}/membership", status_code=204, response_class=Response)
    def leave_club(club_id: int, user_id: int = actor):
        with translate_errors():
            service.leave_club(user_id, club_id)

    @router.get("/{club_id}/members")
    def roster(club_id: int, user_id: int = actor):
        with translate_errors():
            return service.roster(user_id, club_id)

    @router.delete("/{club_id}/members/{student_id}", status_code=204, response_class=Response)
    def remove_member(club_id: int, student_id: int, user_id: int = actor):
        with translate_errors():
            service.remove_member(user_id, club_id, student_id)

    @router.post("", status_code=201)
    def create_club(body: ClubIn, user_id: int = actor):
        with translate_errors():
            return service.create_club(user_id, **body.model_dump())

    @router.put("/{club_id}")
    def update_club(club_id: int, body: ClubIn, user_id: int = actor):
        with translate_errors():
            return service.update_club(user_id, club_id, **body.model_dump())

    return router
