"""Domain events, and the port that delivers them to their handlers."""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Annotated, Protocol
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field


class DomainEvent(BaseModel):
    """Base class for something that happened in the domain.

    A subclass names the event and declares the fields that describe it.
    """

    model_config = ConfigDict(frozen=True)

    event_id: Annotated[UUID, Field(default_factory=uuid7)]
    """The unique ID of the event."""
    timestamp: Annotated[datetime, Field(default_factory=lambda: datetime.now(tz=UTC))]
    """When the event happened, in UTC."""


class DomainEventHandler[T: DomainEvent](Protocol):
    """Reacts to one type of event."""

    async def handle(self, event: T) -> None:
        """React to the event."""
        ...


class EventBroker(Protocol):
    """Delivers events to the handlers subscribed to their types."""

    def subscribe[T: DomainEvent](
        self, event_type: type[T], handler: DomainEventHandler[T]
    ) -> None:
        """Have `handler` receive every event of `event_type` published from now on."""
        ...

    async def publish(self, events: Iterable[DomainEvent]) -> None:
        """Deliver each event, in order, to the handlers subscribed to its type."""
        ...
