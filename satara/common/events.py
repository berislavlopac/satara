from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid7

from pydantic import BaseModel, Field


class DomainEvent(BaseModel):
    """Abstract envelope for all domain events."""

    # TODO: Replace with Annotated when ty supports it: https://github.com/astral-sh/ty/issues/2130
    event_id: UUID = Field(default_factory=uuid7)
    """The unique ID of the event."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    """Date and time of the event object creation."""
    payload: BaseModel
    """Payload of the event; must be a BaseModel subclass."""

    def serialize(self) -> dict[str, Any]:
        return self.payload.model_dump(mode="json")


class DomainEventHandler[T: DomainEvent](Protocol):
    async def handle(self, event: T): ...


class EventBroker(Protocol):
    def subscribe(self, event_type: type[DomainEvent], handler: DomainEventHandler) -> None: ...

    async def publish(self, event: DomainEvent) -> None: ...

    async def publish_all(self, events: Iterable[DomainEvent]) -> None: ...
