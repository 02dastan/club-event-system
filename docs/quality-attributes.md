# Quality Attributes

Measurable quality scenarios from Milestone 1.

## 1. Usability

- **Source/actor:** A student
- **Trigger:** The student opens an available event on a desktop or mobile browser and wants to register.
- **Condition:** The event is visible and registration is open.
- **Response:** The system shows the essential event details, accepts one registration action and displays a confirmation.
- **Success criterion:** At least 95% of test users complete registration in no more than 4 clicks, and confirmation appears within 3 seconds.

## 2. Performance

- **Source/actor:** Up to 500 concurrent students
- **Trigger:** Users search, filter or open event pages during a busy campus announcement period.
- **Condition:** The catalog contains up to 10,000 event records and the network is available.
- **Response:** The system returns the requested catalog or event information without losing the request.
- **Success criterion:** At least 95% of catalog requests complete within 2 seconds; failed requests remain below 1%.

## 3. Security

- **Source/actor:** A logged-in user without organizer or administrator rights
- **Trigger:** The user attempts to edit or cancel another club's event.
- **Condition:** Role checks are enabled and the event belongs to a different club.
- **Response:** The system denies the operation, keeps the event unchanged and records the denied attempt.
- **Success criterion:** 100% of tested unauthorized edit/cancel requests are rejected and no protected event field changes.
