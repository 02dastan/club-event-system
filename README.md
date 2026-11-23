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

## What the app supports

- **Students** search and filter events, join clubs, register for events, and cancel their own registrations.
- **Organizers** publish, edit, and cancel their club's events and manage club members and event participants.
- **Administrators** review organizer requests, assign roles, manage clubs, and control self-service sign-up.
- **Notifications** cover registration confirmations, event reminders, event changes, cancellations, and new
  events from clubs a student has joined.

**Stack** · Python 3.10+, FastAPI, SQLite, HTML, JavaScript, and pytest.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell, use `python -m venv .venv` and `.venv\Scripts\Activate.ps1`.

### Demo for the milestone presentation

```bash
CLUB_EVENTS_DEMO=1 uvicorn app.main:create_app --factory --app-dir src
```

On PowerShell, set `$env:CLUB_EVENTS_DEMO = '1'` and run the `uvicorn` command separately.
Open [the app](http://127.0.0.1:8000). The demo uses `club_events_demo.db` and starts with sample users and the SDU Robotics Club.

1. Choose **Club Organizer** and publish an event with a future start time.
2. Switch to **Student One**, find the event using the catalog, and register. A repeat attempt shows the duplicate rule.
3. Open the notification outbox and choose **Send pending notifications**. The status changes to `SENT` and the simulated message goes to the server console.
4. Open **My registrations** to cancel the booking, then switch back to the organizer to edit or cancel the event.

### Run with real accounts

```bash
export CLUB_EVENTS_ADMIN_EMAIL=admin@example.com
printf 'Initial administrator password: '
IFS= read -rs CLUB_EVENTS_ADMIN_PASSWORD
printf '\n'
export CLUB_EVENTS_ADMIN_PASSWORD
uvicorn app.main:create_app --factory --app-dir src
```

Use a unique administrator password of at least 12 characters. The two administrator variables create
the first administrator when the database has no administrator account. The normal app uses account
sessions for identity. If your shell still has demo mode enabled, run `unset CLUB_EVENTS_DEMO` on
macOS/Linux or `Remove-Item Env:CLUB_EVENTS_DEMO` in PowerShell before starting this mode.

1. Sign up as a student and submit an organizer request from the account screen.
2. Sign in as the administrator, approve the request, then create a club and select the approved organizer.
3. Sign in as that organizer to publish the club's first event. Other students can browse the catalog and join.

The default database is `club_events.db`. Set `CLUB_EVENTS_DB` to use a different SQLite file in either mode.
The [API reference](http://127.0.0.1:8000/docs) lists the endpoints. Use HTTPS for a hosted installation.

### Telegram and e-mail delivery

| Environment variable | Purpose |
|---|---|
| `SMTP_HOST` | SMTP relay for students with no Telegram link. |
| `SMTP_PORT` | Relay port, with `25` as the default. |
| `SMTP_FROM` | Sender address accepted by the relay. The default is `events@sdu.edu.kz`. |
| `TELEGRAM_BOT_TOKEN` | Token for the project bot, supplied through the environment. |
| `TELEGRAM_BOT_USERNAME` | Bot username used to generate the link from the account screen. |

Configure the channels you want to use. In the normal app, the worker polls and dispatches automatically on a
60-second interval. Run one application worker for the notification dispatcher. To receive Telegram messages,
generate a link in the account screen, open it, and press **Start** in the bot chat within 10 minutes. E-mail
delivery requires an SMTP relay. The account screen also lets a user unlink Telegram and return to e-mail.

### Run the tests

```bash
python -m pytest -v
```

The tests use in-memory or temporary SQLite databases and substitute the notification transports.

## Code structure

```
src/app/
  main.py            composition root and notification worker lifecycle
  database.py        SQLite connections, write transactions, and demo data
  users/             accounts, sessions, access, audit log, and user contacts
  clubs/             clubs, memberships, and organizer rosters
  events/            event catalog and organizer workflows
  registrations/     registration, cancellation, capacity, and participant lists
  notifications/     outbox, reminders, Telegram linking, and transport adapters
  static/            responsive web app served by FastAPI
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
