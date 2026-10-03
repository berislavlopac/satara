import pytest

from satara.common.events import DomainEvent
from satara.infrastructure.events import InProcessEventBroker


class Happened(DomainEvent):
    what: str


class Other(DomainEvent):
    pass


class Recorder:
    def __init__(self, name, log):
        self.name = name
        self.log = log

    async def handle(self, event):
        self.log.append((self.name, event.what))


class Failing:
    async def handle(self, event):
        raise RuntimeError("handler failed")


async def test_in_process_broker_delivers_each_event_to_its_subscribers_in_order():
    log = []
    broker = InProcessEventBroker()
    broker.subscribe(Happened, Recorder("first", log))
    broker.subscribe(Happened, Recorder("second", log))

    await broker.publish([Happened(what="a"), Other(), Happened(what="b")])

    assert log == [("first", "a"), ("second", "a"), ("first", "b"), ("second", "b")]


async def test_in_process_broker_lets_a_handler_failure_reach_the_publisher():
    broker = InProcessEventBroker()
    broker.subscribe(Happened, Failing())

    with pytest.raises(RuntimeError):
        await broker.publish([Happened(what="a")])
