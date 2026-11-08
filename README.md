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

## Architecture

Modular monolith (Users, Clubs, Events, Registrations, Notifications) with an adapter around
Telegram and SMTP.

- [Container diagram](docs/architecture/container-diagram.md)
- [Context diagram](docs/architecture/context-diagram.md)
- [Selected architecture](docs/architecture/selected-architecture.md)
- [ADR-001: notification outbox](docs/adr/ADR-001-notification-outbox.md)

## Repository structure

- `docs/requirements.md` - functional requirements and constraints
- `docs/stakeholders.md` - problem, scope, stakeholders and needs
- `docs/quality-attributes.md` - measurable quality scenarios
- `docs/architecture/` - context and container diagrams, selected architecture
- `docs/adr/` - architecture decision records
- `src/` - source code (Milestone 3)

## Status

Milestone 2 complete. Milestone 3 (working prototype) in progress.
