# Selected Architecture

## Style

Modular monolith with layers inside each module, and an adapter around the external notification channels.
One Backend API contains the modules **Users, Clubs, Events, Registrations and Notifications**.
Inside each module the layers are **controller -> service -> repository**.

## Dependency rules

1. Layers call only downward.
2. A module uses another module only through its service interface, never its repository or tables.
3. Business modules never call Telegram or SMTP; they only enqueue messages through the Notifications module (ADR-001).

## Data ownership

| Module | Owns |
|---|---|
| Users | accounts, roles, audit log of denied actions |
| Clubs | clubs, memberships |
| Events | events |
| Registrations | registrations |
| Notifications | notification outbox |

## Why it fits

Registration needs one transaction and a database uniqueness rule (one registration per student per event).
One backend with one database provides this without distributed coordination, and a team of four can build,
test and deploy one backend and one web app.

## Quality attributes supported

- **Usability:** registration commits one local transaction and returns at once; notifications are sent later
  by the dispatcher, so Telegram or SMTP delays never block the student. This supports the 3-second confirmation target.
- **Security:** role and club-ownership checks sit in the service layer of the Backend API, so every entry point
  passes through them and the web app is never trusted. Denied attempts are written to an audit log.
  This supports the target of rejecting 100% of unauthorized edits and cancellations.

## Benefit and cost

- **Benefit:** a change such as a new notification channel stays inside one module (one new adapter).
- **Cost:** module boundaries can erode inside one deployable application, and the whole application scales and
  fails together. The dependency rules above are our guard against the first risk.

## Alternative considered

**Hexagonal architecture** (ports and adapters for every dependency). Not selected because our domain is mostly
CRUD with little logic worth isolating, and interfaces for every repository add code without benefit for a
four-person team. We apply the port idea only where the dependency is unstable: notifications (ADR-001).
