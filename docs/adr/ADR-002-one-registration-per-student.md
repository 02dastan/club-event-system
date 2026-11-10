# ADR-002: Enforce "one registration per student per event" in the database and in one transaction

**Status:** Accepted

## Context

FR3 says a student cannot register twice for the same event, and the event capacity must not be exceeded.
A student can double-click the Register button, or send two requests at the same time. A check in code
("is the student already registered?") followed by an insert leaves a gap: two requests can both pass
the check before either one saves. Each registration must also put exactly one confirmation into the
notification outbox (ADR-001).

## Decision

1. The `registrations` table has a `UNIQUE (event_id, student_id)` constraint. This is the final guard.
2. `RegistrationService` still checks `exists()` first, so the normal case returns a clear message.
   If the insert hits the constraint anyway, the repository turns the database error into
   `DuplicateRegistration` (HTTP 409).
3. The duplicate check, the capacity check, the insert and the outbox message run in **one transaction**.
   If any step fails, nothing is saved: no registration without a message, no message without a registration.
4. The service receives the transaction as an injected function, so unit tests can use a real
   in-memory database or a fake.

## Alternatives considered

- **Check only in the service code.** Simple, but not safe for two simultaneous requests.
- **Constraint only, no check in code.** Safe, but every duplicate becomes a database error, and the
  error type would leak from the repository into the business layer.
- **Lock the event row before registering.** Also solves capacity races, but SQLite has no row locks,
  and it adds complexity that a campus-size load does not need yet.

## Consequences

**Positive**
- Double registration is impossible even with parallel requests.
- One clear error (409) for the user in both paths.
- Registration and its confirmation are always consistent.

**Negative**
- The rule exists in two places (service and schema); both must change together.
- The capacity check is still check-then-insert. With parallel requests the last seat could be
  over-booked by one; we accept this for the prototype and would add row locking with PostgreSQL.

## How it is checked

`test_student_cannot_register_twice_for_the_same_event`, `test_registration_rejected_when_event_is_full`,
`test_registration_is_rolled_back_if_outbox_write_fails`.
