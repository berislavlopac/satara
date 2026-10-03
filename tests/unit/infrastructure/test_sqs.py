import json

import pytest

from satara.infrastructure.sqs import SQSMessageQueue


@pytest.fixture
def create_queue(sqs_client):
    """Create a queue that delivers a message again at once if it is not deleted."""

    async def create_queue(name, max_attempts=None):
        attributes = {"VisibilityTimeout": "0"}
        if max_attempts is not None:
            dead_letter = await sqs_client.create_queue(QueueName=f"{name}-dead-letter")
            dead_letter_arn = (
                await sqs_client.get_queue_attributes(
                    QueueUrl=dead_letter["QueueUrl"], AttributeNames=["QueueArn"]
                )
            )["Attributes"]["QueueArn"]
            policy = {"deadLetterTargetArn": dead_letter_arn, "maxReceiveCount": max_attempts}
            attributes["RedrivePolicy"] = json.dumps(policy)
        response = await sqs_client.create_queue(QueueName=name, Attributes=attributes)
        return SQSMessageQueue(sqs_client, response["QueueUrl"], wait_seconds=0)

    return create_queue


async def test_queue_gives_each_message_with_the_attempt_it_is_on(sqs_client, create_queue):
    queue = await create_queue("uploads")
    url = (await sqs_client.get_queue_url(QueueName="uploads"))["QueueUrl"]
    await sqs_client.send_message(QueueUrl=url, MessageBody="hello")

    first, second = await queue.receive(), await queue.receive()

    assert [(message.body, message.attempt) for message in first + second] == [
        ("hello", 1),
        ("hello", 2),
    ]


async def test_queue_does_not_deliver_a_deleted_message_again(sqs_client, create_queue):
    queue = await create_queue("uploads")
    url = (await sqs_client.get_queue_url(QueueName="uploads"))["QueueUrl"]
    await sqs_client.send_message(QueueUrl=url, MessageBody="hello")
    [message] = await queue.receive()

    await queue.delete(message)

    assert await queue.receive() == []


@pytest.mark.parametrize(
    ("max_attempts", "expected"), [(3, 3), (None, None)], ids=["redrive policy", "none"]
)
async def test_queue_reads_its_attempts_from_the_redrive_policy(
    create_queue, max_attempts, expected
):
    queue = await create_queue("uploads", max_attempts=max_attempts)

    result = await queue.read_max_attempts()

    assert result == expected
