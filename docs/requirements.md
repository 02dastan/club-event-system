# Requirements and Constraints

## Essential functional requirements

| ID | Requirement |
|---|---|
| FR1 | Students can browse and search the event catalog, filtering results by date, category or hosting club. |
| FR2 | Club organizers can create, edit and cancel event announcements containing a title, description, date, time, venue and category. |
| FR3 | Students can register for an event in one action, cancel their registration, and cannot register twice for the same event. |
| FR4 | Students can join or leave clubs, and organizers can view and manage their club's member roster. |
| FR5 | The system sends reminders and announcement notifications through the configured notification channel: reminders, changes and cancellations to students registered for an event, and announcements of new events to members of the hosting club. *(Updated in Milestone 2.)* |
| FR6 | Administrators can manage user roles, approve club-organizer accounts and configure platform settings. |

## Constraints

| ID | Constraint |
|---|---|
| C1 | The platform will not process payments or support paid ticketing. |
| C2 | The system must work in standard desktop and mobile web browsers without a native mobile application. |
| C3 | Automated notifications must use free-tier channels such as the Telegram Bot API or SMTP, without paid API subscriptions. |

## Clarifications added in Milestone 2

1. FR5 now covers two recipient groups: students registered for an event, and members of the hosting club.
   Reason: the "Club members" stakeholder needed notifications about new club events, which FR5 did not cover.
2. Users sign in with their own accounts; organizer accounts need administrator approval.
   Reason: Milestone 1 required logged-in roles but did not say where accounts come from.
3. Telegram is linked with a one-time code issued in the web app; until then e-mail is used.
   Reason: a Telegram bot cannot message a user who has not started it.
