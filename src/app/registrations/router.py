"""HTTP layer of the Registrations module."""
from fastapi import APIRouter, Depends, HTTPException

from ..events.service import EventNotFound
from ..users.access import PermissionDenied
from .repository import DuplicateRegistration
from .service import RegistrationClosed, RegistrationService


def make_router(service: RegistrationService, current_user_id) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["registrations"])

    @router.get("/registrations/me")
    def my_registrations(user_id: int = Depends(current_user_id)):
        try:
            return service.for_student(user_id)
        except PermissionDenied as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    @router.post("/events/{event_id}/registrations", status_code=201)
    def register(event_id: int, user_id: int = Depends(current_user_id)):
        try:
            registration = service.register(user_id, event_id)
        except EventNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionDenied as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except (DuplicateRegistration, RegistrationClosed) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"registration": registration,
                "message": "Registered. A confirmation will be sent to you."}

    @router.delete("/events/{event_id}/registrations/me", status_code=204)
    def cancel(event_id: int, user_id: int = Depends(current_user_id)):
        try:
            service.cancel(user_id, event_id)
        except EventNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionDenied as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    @router.get("/events/{event_id}/registrations")
    def participants(event_id: int, user_id: int = Depends(current_user_id)):
        try:
            return service.participants(user_id, event_id)
        except EventNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionDenied as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    @router.delete("/events/{event_id}/registrations/{student_id}", status_code=204)
    def remove_participant(event_id: int, student_id: int, user_id: int = Depends(current_user_id)):
        try:
            service.remove_participant(user_id, event_id, student_id)
        except EventNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionDenied as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    return router
