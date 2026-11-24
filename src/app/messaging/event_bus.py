"""Simple in-process event bus.

A publisher calls publish(event) and does not know who reacts to it.
Consumers register with subscribe(EventType, handler).
"""
from collections import defaultdict
from typing import Callable


class EventBus:
    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event) -> None:
        for handler in self._handlers[type(event)]:
            handler(event)