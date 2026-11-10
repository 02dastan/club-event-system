"""Notifications module: sends pending outbox messages through the right adapter."""
from dataclasses import dataclass

from ..users.contacts import UserDirectory
from .outbox import SqliteOutbox
from .sender import DeliveryError, NotificationSender


@dataclass
class DispatchResult:
    sent: int = 0
    failed_attempts: int = 0


class NotificationDispatcher:
    MAX_ATTEMPTS = 5

    def __init__(self, outbox: SqliteOutbox, contacts: UserDirectory,
                 senders: dict[str, NotificationSender]):
        # senders maps a channel name ("telegram", "email") to an adapter.
        # The composition root chooses the adapters; this class depends only on the port.
        self._outbox = outbox
        self._contacts = contacts
        self._senders = senders

    def dispatch_pending(self, batch_size: int = 20) -> DispatchResult:
        result = DispatchResult()
        for message in self._outbox.pending(batch_size):
            contact = self._contacts.contact_for(message.recipient_id)
            sender = self._senders.get(contact.channel) if contact else None
            try:
                if sender is None:
                    raise DeliveryError(f"No channel for user {message.recipient_id}")
                sender.send(contact.address, message.text)
            except DeliveryError:
                self._outbox.mark_attempt_failed(message.id, self.MAX_ATTEMPTS)
                result.failed_attempts += 1
            else:
                self._outbox.mark_sent(message.id)
                result.sent += 1
        return result
