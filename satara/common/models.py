from typing import Annotated
from uuid import UUID, uuid7

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    model_serializer,
    model_validator,
)

from .events import DomainEvent
from .validators import validate_uuid7


class FrozenModel(BaseModel):
    """Base class for immutable models."""

    model_config = ConfigDict(frozen=True)


class Entity(BaseModel):
    """Base class for models representing entities."""

    _events: list[DomainEvent] = []
    """Internal list of events related to this entity."""

    def set_event(self, event: DomainEvent):
        self._events.append(event)

    def get_events(self) -> list[DomainEvent]:
        return self._events


class IDModel(FrozenModel):
    """Base class for models representing various identifiers."""

    id: Annotated[UUID, BeforeValidator(validate_uuid7)]

    @classmethod
    def generate(cls):
        """Generates a random ID instance."""
        return cls(id=uuid7())

    def __str__(self):
        return str(self.id)

    @model_serializer(mode="plain")
    def serialize_model(self) -> str:
        return str(self)

    @model_validator(mode="before")
    @classmethod
    def parse_raw_uuid(cls, value):
        # If the input is a raw UUID or string, wrap it in a dict
        if isinstance(value, (UUID, str)):
            return {"id": value}
        return value
