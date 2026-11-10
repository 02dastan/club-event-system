"""Notifications module: the NotificationSender port and its adapters (Adapter pattern).

Our code needs one simple operation: send(address, text).
Telegram and SMTP offer different, incompatible interfaces:
  - Telegram Bot API: send_message(chat_id: int, text) -> {"ok": bool, "description": ...}
  - SMTP (smtplib):   send_message(EmailMessage) with From/To/Subject headers, raises on error
Each adapter translates our call into the external interface and turns its
failure style into one DeliveryError. The dispatcher only knows NotificationSender.
"""
import logging
import smtplib
from email.message import EmailMessage
from typing import Callable, Protocol

log = logging.getLogger("notifications")


class DeliveryError(Exception):
    """The external channel could not deliver the message."""


class NotificationSender(Protocol):
    """Port: what the Notifications module needs from any channel."""

    def send(self, address: str, text: str) -> None: ...


# ---------- Telegram ----------

class TelegramBotApi(Protocol):
    """Shape of the Telegram Bot API client (adaptee)."""

    def send_message(self, chat_id: int, text: str) -> dict: ...


class TelegramAdapter:
    """Adapter: NotificationSender -> Telegram Bot API."""

    def __init__(self, api: TelegramBotApi):
        self._api = api

    def send(self, address: str, text: str) -> None:
        try:
            result = self._api.send_message(chat_id=int(address), text=text)
        except Exception as e:  # network error, timeout, invalid chat id
            raise DeliveryError(f"Telegram: {e}") from e
        if not result.get("ok", False):
            raise DeliveryError(f"Telegram: {result.get('description', 'unknown error')}")


class HttpTelegramBotApi:
    """Real client for https://api.telegram.org (used only when a bot token is configured)."""

    def __init__(self, token: str, timeout: float = 5.0):
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._timeout = timeout

    def send_message(self, chat_id: int, text: str) -> dict:
        import json
        import urllib.request
        body = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(self._url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return json.load(resp)


class ConsoleTelegramBotApi:
    """Development stand-in: prints instead of calling Telegram."""

    def send_message(self, chat_id: int, text: str) -> dict:
        log.info("[telegram -> %s] %s", chat_id, text)
        return {"ok": True}


# ---------- E-mail ----------

class SmtpAdapter:
    """Adapter: NotificationSender -> SMTP server."""

    SUBJECT = "SDU Club Events"

    def __init__(self, smtp_factory: Callable[[], smtplib.SMTP], from_address: str):
        self._smtp_factory = smtp_factory
        self._from = from_address

    def send(self, address: str, text: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._from
        msg["To"] = address
        msg["Subject"] = self.SUBJECT
        msg.set_content(text)
        try:
            with self._smtp_factory() as smtp:
                smtp.send_message(msg)
        except Exception as e:  # smtplib.SMTPException, OSError
            raise DeliveryError(f"SMTP: {e}") from e


class ConsoleSmtp:
    """Development stand-in for smtplib.SMTP: prints the e-mail."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send_message(self, msg: EmailMessage) -> None:
        log.info("[email -> %s] %s", msg["To"], msg.get_content().strip())
