from collections.abc import Hashable
from typing import Annotated, Self
from uuid import UUID, uuid7

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    PrivateAttr,
    model_serializer,
    model_validator,
)

from .events import DomainEvent
from .validators import validate_uuid7


class FrozenModel(BaseModel):
    """Base class for immutable models."""

    model_config = ConfigDict(frozen=True)


class ValueObject(FrozenModel):
    """Base class for value objects.

    A value object has no identity: two instances with equal fields are the same value.
    """


class Entity(BaseModel):
    """Base class for entities, compared and hashed by identity.

    Entities are mutable, so equality and hashing use `identity` rather than the fields. An
    entity stays equal to itself, and safe as a set or dict key, as its state changes.
    Subclasses override the `identity` property.
    """

    _events: list[DomainEvent] = PrivateAttr(default_factory=list)
    """The events recorded and not yet pulled."""

    @property
    def identity(self) -> Hashable:
        """The value identifying this entity among others of its type.

        Raises:
            NotImplementedError: A subclass does not override this property.
        """
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity) or type(self) is not type(other):
            return NotImplemented
        return self.identity == other.identity

    def __hash__(self) -> int:
        return hash((type(self).__name__, self.identity))

    def record_event(self, event: DomainEvent) -> None:
        """Record an event, to be published once the change that caused it is saved."""
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """Return the events recorded so far and forget them, so each is published once."""
        events, self._events = self._events, []
        return events


class IDModel(ValueObject):
    """Base class for identifiers, holding a UUID7."""

    id: Annotated[UUID, BeforeValidator(validate_uuid7)]

    @classmethod
    def generate(cls) -> Self:
        """Generate a new, unique ID."""
        return cls(id=uuid7())

    def __str__(self) -> str:
        return str(self.id)

    @model_serializer(mode="plain")
    def serialize_model(self) -> str:
        return str(self)

    @model_validator(mode="before")
    @classmethod
    def parse_raw_uuid(cls, value: object) -> object:
        # If the input is a raw UUID or string, wrap it in a dict
        if isinstance(value, (UUID, str)):
            return {"id": value}
        return value
