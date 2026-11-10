# ADR-001: Deliver notifications through a transactional outbox and a notification port

**Status:** Accepted (updated in Milestone 3, see the last section)

## Context

FR5 requires reminders and announcements through free-tier channels only, the Telegram Bot API or SMTP
(Constraint C3). These channels are slow and sometimes unavailable, while registration must confirm within
3 seconds (Usability scenario). How should the Backend API depend on the external Notification service?

## Decision

Business modules never call Telegram or SMTP. A registration or event change saves an outbox record in the
same database transaction. A scheduled dispatcher inside the Backend API reads pending records in small batches,
expands them into recipients and sends them through a `NotificationSender` interface, implemented by
`TelegramAdapter` and `SmtpAdapter` (Adapter pattern; the application setup supplies the adapters, so the
dispatcher depends only on the interface). Failed sends are retried up to 5 times, then marked failed.

## Alternatives considered

- **A. Send inside the request.** Simplest, but a Telegram or SMTP outage would break registration and the 3 s target.
- **B. In-memory background task, no outbox table.** No extra table, but pending messages are lost when the API restarts.
- **C. Separate worker container with a broker (RabbitMQ, Redis).** Best isolation, but one or two more containers
  to build and run, which is not justified for about 10,000 events and a campus-size load.

## Consequences

**Positive**
- Registration does not wait for Telegram or SMTP.
- Messages survive restarts and outages.
- A new channel is one new adapter.
- No new container or paid service.

**Negative**
- Delivery is delayed by the polling interval (seconds to a minute).
- The dispatcher shares CPU and memory with the API and must run in one process (several instances would need row locking).
- A crash can cause a rare duplicate message.
- The outbox table needs cleanup and monitoring.

## How it is checked

Block Telegram and SMTP for 2 minutes and register for an event: the confirmation must appear within 3 s,
and the message must be delivered within 10 minutes of the registration after the channel is restored.

## Update after implementation (Milestone 3)

The decision stands. Three details changed when we built it:

1. **Dispatcher trigger.** In the prototype the dispatcher runs when `POST /api/notifications/dispatch`
   is called (a button on the demo page), not on a timer. This makes the outbox visible in the demo and
   avoids sharing one SQLite connection between a background thread and request threads. A scheduler
   that calls the same `dispatch_pending()` method can be added later without changing other code.
2. **Channel per user.** The dispatcher receives a map of adapters (`telegram`, `email`) and asks the
   Users module (`UserDirectory`) which channel a user has: Telegram if linked, otherwise e-mail.
3. **Development mode.** Without `TELEGRAM_BOT_TOKEN` or `SMTP_HOST`, the adapters wrap console
   stand-ins, so the project runs without accounts or network. Tests always use fake senders.

Retry rule is implemented as decided: each failed send increases `attempts`; after 5 the message is `FAILED`.
Checked by `test_registration_succeeds_while_notification_channels_are_down` and
`test_message_is_marked_failed_after_five_attempts`.
