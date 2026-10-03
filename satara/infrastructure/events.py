"""An event broker that delivers events within the process that publishes them."""

from collections.abc import Iterable

from satara.common.events import DomainEvent, DomainEventHandler


class InProcessEventBroker:
    """Delivers each event to the handlers subscribed to its type, one after another.

    Delivery happens inside `publish`, so a handler's failure reaches the publisher.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[DomainEventHandler]] = {}

    def subscribe[T: DomainEvent](
        self, event_type: type[T], handler: DomainEventHandler[T]
    ) -> None:
        """Have `handler` receive every event of `event_type` published from now on."""
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, events: Iterable[DomainEvent]) -> None:
        """Deliver each event, in order, to the handlers subscribed to its exact type."""
        for event in events:
            for handler in self._handlers.get(type(event), []):
                await handler.handle(event)
