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
from typing import Callable, Optional, Protocol

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
        self._url = f"https://api.telegram.org/bot{token}"
        self._timeout = timeout

    def send_message(self, chat_id: int, text: str) -> dict:
        return self._post("sendMessage", {"chat_id": chat_id, "text": text})

    def get_updates(self, offset: Optional[int] = None) -> list[dict]:
        payload = {"allowed_updates": ["message"], "timeout": 0}
        if offset is not None:
            payload["offset"] = offset
        result = self._post("getUpdates", payload)
        if not result.get("ok") or not isinstance(result.get("result"), list):
            raise DeliveryError("Telegram refused the update request.")
        return result["result"]

    def _post(self, method: str, payload: dict) -> dict:
        import json
        import urllib.request
        body = json.dumps(payload).encode()
        req = urllib.request.Request(f"{self._url}/{method}", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.load(resp)
        except (ValueError, OSError):
            # The underlying exception can contain the bot token in its URL.
            raise DeliveryError(f"Telegram {method} request failed.") from None
        if not isinstance(result, dict):
            raise DeliveryError(f"Telegram {method} returned an invalid response.")
        return result


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
