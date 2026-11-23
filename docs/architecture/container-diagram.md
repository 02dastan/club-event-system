# Container Diagram (C4 level 2)

```mermaid
flowchart TB
    S["Students<br/>[Person]"]
    O["Club organizers<br/>[Person]"]
    A["System administrator<br/>[Person]"]

    subgraph SYS["Student-Club Event Management System"]
        WEB["Web app<br/>[HTML + JavaScript, served by the API]<br/>Catalog, club membership, registrations,<br/>organizer and administrator screens."]
        API["Backend API<br/>[Python, FastAPI, modular monolith]<br/>Users, Clubs, Events, Registrations,<br/>Notifications, and a scheduled dispatcher."]
        DB[("Database<br/>[SQLite]<br/>Accounts, sessions, clubs, events,<br/>registrations, outbox, and audit log.")]
    end

    N["Notification service<br/>[External: Telegram Bot API / SMTP]"]

    S -- "uses in browser" --> WEB
    O -- "uses in browser" --> WEB
    A -- "uses in browser" --> WEB
    WEB -- "REST API and session cookie<br/>[HTTP / JSON, HTTPS when hosted]" --> API
    API -- "reads and writes in<br/>transactions [SQL]" --> DB
    API -- "sends via adapters and polls Telegram<br/>for account-link commands" --> N
    N -- "delivers confirmations,<br/>announcements, and reminders" --> S
```

**Legend.** Boxes inside the frame are containers of our system. Boxes outside are people and the external system.

## Implementation notes

- FastAPI serves the web app as static assets. The browser displays state and submits actions. The API enforces
  role, ownership, registration, and capacity rules.
- SQLite uses a connection per worker thread and explicit write transactions for operations that need to be atomic.
- The API runs the notification dispatcher on a schedule in normal mode. Demo mode uses a manual dispatcher and
  console transport adapters so the queue is visible during the presentation. See [ADR-001](../adr/ADR-001-notification-outbox.md).
