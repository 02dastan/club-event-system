# Student-Club Event Management System

A single place for SDU students to discover, join and organize student-club events.
Course project for CSS 217 Software Architecture and Design Patterns (SDU).

## Problem

Student clubs at SDU struggle with event promotion and coordination because announcements
are fragmented across Instagram, Telegram and WhatsApp. Students miss events because of
information overload, while club leaders lack a reliable way to manage registrations.

## Team

| Student ID | Name |
|---|---|
| 190107049 | Adilet Kaskatayev |
| 240107105 | Bakdaulet Karzhaubay |
| 240107050 | Dastan Tolkynov |
| 240107104 | Atabek Bakhytzhanov |

## Milestone 3 prototype

**User flow:** an organizer creates an event, a student registers for it and sees a confirmation;
the confirmation message is saved in the notification outbox in the same transaction (ADR-001) and the
dispatcher sends it through the Telegram or e-mail adapter.

**Demo steps:** open the page, act as *Club Organizer* and create an event; switch to *Student One* and
press *Register*; press *Register* again to see the duplicate rule; switch to *Club Organizer* and press
*Register* to see the permission rule; press *Send pending notifications* and watch the outbox status
change to SENT (messages are printed in the server console).

**Stack:** Python 3.10+, FastAPI, SQLite, pytest.

### Setup and run

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:create_app --factory --reload --app-dir src
```

Open http://127.0.0.1:8000 for the web page, or http://127.0.0.1:8000/docs for the API.
The database file `club_events.db` is created on first start with demo users
(user 1 = organizer of SDU Robotics Club, users 2 and 3 = students).
Delete the file to start again from empty data.

### Run the tests

```bash
pytest -v
```

Tests use an in-memory database and fake notification senders. They never call Telegram or SMTP.

### Optional: real notification channels

```bash
set TELEGRAM_BOT_TOKEN=<bot token>      # Windows (use export on macOS / Linux)
set SMTP_HOST=<smtp server>
set SMTP_PORT=25
set SMTP_FROM=events@sdu.edu.kz
```

Without these variables the adapters print messages to the server console.

## Code structure

```
src/app/
  main.py            composition root: chooses concrete classes and wires modules
  database.py        SQLite connection, tables, demo data
  events/            Events module: router -> service -> repository
  registrations/     Registrations module: one registration per student, capacity
  notifications/     outbox, dispatcher, NotificationSender + Telegram/SMTP adapters
  users/             access rules, audit log, user contact channel
  static/index.html  simple web page
tests/               automated tests
```

Each module follows the layers controller (router) -> service -> repository.
A module uses another module only through its service (see selected architecture).

## Architecture documents

- [Container diagram](docs/architecture/container-diagram.md)
- [Context diagram](docs/architecture/context-diagram.md)
- [Selected architecture](docs/architecture/selected-architecture.md)
- [Class diagram of the implemented flow](docs/architecture/class-diagram.md)
- [ADR-001: notification outbox](docs/adr/ADR-001-notification-outbox.md)
- [ADR-002: one registration per student](docs/adr/ADR-002-one-registration-per-student.md)

## Repository structure

- `docs/requirements.md` - functional requirements and constraints
- `docs/stakeholders.md` - problem, scope, stakeholders and needs
- `docs/quality-attributes.md` - measurable quality scenarios
- `docs/architecture/` - diagrams and selected architecture
- `docs/adr/` - architecture decision records
- `src/` - source code
- `tests/` - automated tests
