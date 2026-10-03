import pytest

from satara.infrastructure.events import InProcessEventBroker


async def test_in_process_broker_delivers_each_event_to_its_subscribers_in_order(
    sample_event, other_event, recording_handler
):
    log = []
    broker = InProcessEventBroker()
    broker.subscribe(sample_event, recording_handler("first", log))
    broker.subscribe(sample_event, recording_handler("second", log))
    events = [sample_event(label="a"), other_event(), sample_event(label="b")]

    await broker.publish(events)

    assert log == [("first", "a"), ("second", "a"), ("first", "b"), ("second", "b")]


async def test_in_process_broker_lets_a_handler_failure_reach_the_publisher(
    sample_event, failing_handler
):
    broker = InProcessEventBroker()
    broker.subscribe(sample_event, failing_handler)

    with pytest.raises(RuntimeError):
        await broker.publish([sample_event(label="a")])
