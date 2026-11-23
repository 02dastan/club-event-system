"""Club management and membership rules."""
from dataclasses import dataclass
from typing import Callable, ContextManager

from ..users.access import AccessPolicy
from .repository import Club, SqliteClubRepository


class ClubNotFound(Exception):
    pass


class ClubValidationError(Exception):
    pass


@dataclass(frozen=True)
class ClubMember:
    id: int
    name: str


class ClubService:
    def __init__(self, repository: SqliteClubRepository, access: AccessPolicy, *,
                 transaction: Callable[[], ContextManager]):
        self._repository = repository
        self._access = access
        self._transaction = transaction

    def list_clubs(self) -> list[Club]:
        return self._repository.list_all()

    def get_club(self, club_id: int) -> Club:
        club = self._repository.get(club_id)
        if club is None:
            raise ClubNotFound(f"Club {club_id} not found")
        return club

    def create_club(self, user_id: int, name: str, description: str, organizer_id: int) -> Club:
        with self._transaction():
            if self._access.role_of(user_id) == "admin":
                self._validate(name, organizer_id)
                return self._repository.add(name.strip(), description, organizer_id)
        raise self._access.deny(user_id, "create club", name)

    def update_club(self, user_id: int, club_id: int, name: str, description: str,
                    organizer_id: int) -> Club:
        with self._transaction():
            self.get_club(club_id)
            if self._access.role_of(user_id) == "admin":
                self._validate(name, organizer_id)
                return self._repository.update(club_id, name.strip(), description, organizer_id)
        raise self._access.deny(user_id, "edit club", str(club_id))

    def memberships_for(self, student_id: int) -> list[int]:
        return self._repository.memberships_for(student_id)

    def member_ids(self, club_id: int) -> list[int]:
        return self._repository.member_ids(club_id)

    def join_club(self, student_id: int, club_id: int) -> None:
        with self._transaction():
            self.get_club(club_id)
            if self._access.is_student(student_id):
                self._repository.add_member(club_id, student_id)
                return
        raise self._access.deny(student_id, "join club", str(club_id))

    def leave_club(self, student_id: int, club_id: int) -> None:
        with self._transaction():
            self.get_club(club_id)
            self._repository.remove_member(club_id, student_id)

    def roster(self, user_id: int, club_id: int) -> list[ClubMember]:
        self.get_club(club_id)
        if not self._access.is_club_organizer(user_id, club_id):
            raise self._access.deny(user_id, "view club members", str(club_id))
        ids = self.member_ids(club_id)
        names = self._access.names_for(ids)
        return [ClubMember(student_id, names[student_id]) for student_id in ids]

    def remove_member(self, user_id: int, club_id: int, student_id: int) -> None:
        with self._transaction():
            self.get_club(club_id)
            if self._access.is_club_organizer(user_id, club_id):
                self._repository.remove_member(club_id, student_id)
                return
        raise self._access.deny(user_id, "remove club member", str(club_id))

    def _validate(self, name: str, organizer_id: int) -> None:
        if not name.strip():
            raise ClubValidationError("Club name must not be empty")
        if self._access.role_of(organizer_id) != "organizer":
            raise ClubValidationError("Choose an approved organizer for the club")
