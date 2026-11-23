# ADR-001: Deliver notifications through a transactional outbox and a notification port

**Status** · Accepted

## Context

FR5 requires reminders and announcements through free-tier channels only, the Telegram Bot API or SMTP
(Constraint C3). These channels are slow and sometimes unavailable, while registration must confirm within
3 seconds (Usability scenario). How should the Backend API depend on the external Notification service?

## Decision

Business modules enqueue messages through the Notifications module. The registration or event mutation and its
outbox records share the same database transaction. A scheduled dispatcher reads pending records in small batches
and sends them through a `NotificationSender` interface. `TelegramAdapter` and `SmtpAdapter` translate delivery
to their respective services. A message is marked `FAILED` after five failed attempts.

## Alternatives considered

- **A. Send inside the request.** A Telegram or SMTP outage would break registration and the 3 s target.
- **B. In-memory background task.** Pending messages would be lost when the API restarts.
- **C. Separate worker container with a broker (RabbitMQ, Redis).** Best isolation, but one or two more containers
  to build and run, which is not justified for about 10,000 events and a campus-size load.

## Consequences

**Positive**
- Registration does not wait for Telegram or SMTP.
- Messages survive restarts and outages.
- A new channel is one new adapter.
- No new container or paid service.

**Negative**
- Delivery is asynchronous and depends on the polling interval and pending batch size.
- The dispatcher shares CPU and memory with the API and must run in one process (several instances would need row locking).
- A crash can cause a rare duplicate message.
- The outbox table needs cleanup and monitoring.

## How it is checked

The original quality scenario calls for registration confirmation within 3 seconds during a 2-minute transport
outage and delivery within 10 minutes of registration after the channel recovers. The automated tests use fake
transports to verify that failures leave registration intact, retries reach the attempt limit, and the application
worker enqueues and delivers a scheduled reminder without a manual dispatch request.

## Implementation

1. **Automatic worker.** The normal app runs a scheduler on a 60-second interval. It polls Telegram for link
   commands when configured, queues due reminders, and processes the outbox through configured transports.
2. **Recipients and reminders.** New event announcements go to club members. Event updates, cancellations, and
   reminders go to registered students. The reminder job looks 24 hours ahead and queues each student at most once
   per scheduled start time.
3. **Channel per user.** The Users module chooses Telegram for a linked chat and e-mail for other accounts.
   Telegram linking uses a one-time `/start` code that expires after 10 minutes. E-mail delivery uses an SMTP relay.
4. **Presentation demo.** Demo mode uses console stand-ins. The outbox view and manual dispatcher
   (`POST /api/notifications/dispatch`) are available in that mode for tracing the flow.
