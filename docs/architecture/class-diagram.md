# Class diagram: "create and register for an event"

```mermaid
classDiagram
    direction LR
    class RegistrationService {
        +register(student_id, event_id) Registration
    }
    class EventService {
        +create_event(user_id, NewEvent) Event
        +get_event(event_id) Event
    }
    class AccessPolicy {
        +is_student(user_id) bool
        +is_club_organizer(user_id, club_id) bool
        +deny(user_id, action, target) PermissionDenied
    }
    class SqliteRegistrationRepository {
        +add(event_id, student_id, created_at)
        +exists(event_id, student_id) bool
        +count_for_event(event_id) int
    }
    class SqliteOutbox {
        +enqueue(recipient_id, text)
        +pending(limit)
        +mark_sent(id)
        +mark_attempt_failed(id, max)
    }
    class NotificationDispatcher {
        +dispatch_pending() DispatchResult
    }
    class UserDirectory {
        +contact_for(user_id) Contact
    }
    class NotificationSender {
        <<interface>>
        +send(address, text)
    }
    class TelegramAdapter {
        +send(address, text)
    }
    class SmtpAdapter {
        +send(address, text)
    }
    class TelegramBotApi {
        <<external>>
        +send_message(chat_id:int, text) dict
    }
    class SMTP {
        <<external>>
        +send_message(EmailMessage)
    }

    RegistrationService --> EventService : get_event
    RegistrationService --> AccessPolicy
    RegistrationService --> SqliteRegistrationRepository
    RegistrationService --> SqliteOutbox : enqueue (same transaction)
    EventService --> AccessPolicy
    NotificationDispatcher --> SqliteOutbox
    NotificationDispatcher --> UserDirectory
    NotificationDispatcher --> NotificationSender
    NotificationSender <|.. TelegramAdapter
    NotificationSender <|.. SmtpAdapter
    TelegramAdapter --> TelegramBotApi : adapts
    SmtpAdapter --> SMTP : adapts
```

`app/main.py` (composition root) creates all objects and decides which adapters the dispatcher receives.
Tests replace the adapters with `FakeNotificationSender`.
