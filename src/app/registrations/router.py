"""HTTP layer of the Registrations module."""
from fastapi import APIRouter, Header, HTTPException

from ..events.service import EventNotFound
from ..users.access import PermissionDenied
from .repository import DuplicateRegistration
from .service import RegistrationClosed, RegistrationService


def make_router(service: RegistrationService) -> APIRouter:
    router = APIRouter(prefix="/api/events", tags=["registrations"])

    @router.post("/{event_id}/registrations", status_code=201)
    def register(event_id: int, x_user_id: int = Header(...)):
        try:
            registration = service.register(x_user_id, event_id)
        except EventNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PermissionDenied as e:
            raise HTTPException(status_code=403, detail=str(e))
        except (DuplicateRegistration, RegistrationClosed) as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"registration": registration,
                "message": "Registered. A confirmation will be sent to you."}

    return router
