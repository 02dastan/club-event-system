# Container Diagram (C4 level 2), updated in Milestone 3

```mermaid
flowchart TB
    S["Students<br/>[Person]"]
    O["Club organizers<br/>[Person]"]
    A["System administrator<br/>[Person]"]

    subgraph SYS["Student-Club Event Management System"]
        WEB["Web app<br/>[HTML + JavaScript, served by the API]<br/>Event list, create-event form,<br/>Register button, outbox view.<br/>Contains no business rules."]
        API["Backend API<br/>[Python, FastAPI, modular monolith]<br/>Users, Clubs, Events, Registrations,<br/>Notifications modules; role checks,<br/>business rules, notification dispatcher."]
        DB[("Database<br/>[SQLite]<br/>users, audit_log, clubs, events,<br/>registrations, notification_outbox")]
    end

    N["Notification service<br/>[External: Telegram Bot API / SMTP]"]

    S -- "uses in browser<br/>[HTTP]" --> WEB
    O -- "uses in browser<br/>[HTTP]" --> WEB
    A -- "uses in browser<br/>[HTTP]" --> WEB
    WEB -- "calls REST API<br/>[HTTP / JSON]" --> API
    API -- "reads and writes in<br/>transactions [SQL]" --> DB
    API -- "sends messages through<br/>TelegramAdapter / SmtpAdapter" --> N
    N -- "delivers confirmations<br/>and reminders" --> S
```

**Legend.** Boxes inside the frame are containers of our system. Boxes outside are people and the external system.

## Changes from Milestone 2

| What changed | Why |
|---|---|
| Technology is now named: FastAPI (Python) for the Backend API, SQLite for the Database. | Chosen for the prototype; one file database needs no server, so every member can run the project. The relational design is unchanged, so moving to PostgreSQL later only changes the repositories. |
| The Web app is a static page served by the Backend API, not a separate single-page app project. | One deployable unit is enough for the prototype. It is still a separate container at run time (runs in the browser). |
| The dispatcher is triggered by an API call (`POST /api/notifications/dispatch`) instead of a timer. | See the update in ADR-001. |
