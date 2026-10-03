# Deployment

The service is not deployed anywhere: its pipeline stops at CI, as [the exercise page](exercise.md#not-included-release-publishing-and-deployment) explains. This page describes what running it for real needs. [Getting started](getting-started.md) covers running it locally.

## One image, two processes

The image holds the service and its queue consumer, which run as separate processes from the same image:

| Process      | Command                                                                                      | Needed for             |
|--------------|----------------------------------------------------------------------------------------------|------------------------|
| The service  | `uvicorn --factory satara.wiring:create_app --host 0.0.0.0 --port 8000`, the image's default | Both flows             |
| The consumer | `python scripts/consumer.py`                                                                 | The deferred flow only |

Both take the same [configuration](configuration.md). The consumer needs no `SATARA_STORAGE_PUBLIC_URL`, as it signs no URLs. The package is not installed, so the image puts it on the import path with `PYTHONPATH=/app`; run outside the image, the consumer's script needs `PYTHONPATH` set to the repository's root, as well as the AWS variables.

The image is built in two stages: the first installs the locked runtime dependencies, and the second holds only those, the service's code and the consumer's script, without the build tools or the tests. Both processes run as an unprivileged user and finish cleanly on a stop signal.

### The service

- It runs as a single server process listening on port 8000. To serve more requests, run more containers.
- The image's health check calls `GET /health` every 30 seconds.
- Uploaded files larger than 1 MiB are written to temporary files under `/tmp` while a request is read. A container with a read-only filesystem therefore needs a writable `tmpfs` on `/tmp`, large enough for the total size limit times the number of requests served at once.

### The consumer

The consumer builds each archive once its files have arrived.

- **Run exactly one.** It handles one batch of messages at a time, which keeps it from building one archive twice. More consumers would need a lock, such as a marker written with S3's conditional write.
- **Its health check** must replace the image's: the consumer serves nothing over HTTP. While it runs, it touches `satara-consumer-alive` in the temporary directory every 15 seconds, so a check can test that the file is recent. The local stack's check fails once the file is a minute old.
- **Restart it if it exits.** A container platform reports an unhealthy container but does not always restart it.
- **On a stop signal** it finishes the batch in hand, then exits. A build that outlasts the platform's grace period is cut off, and its unfinished upload is removed by the bucket's lifecycle rule, below.

## Storage and queues

The deferred flow needs an S3 bucket and two SQS queues:

- **The bucket** notifies the upload queue of every object created under `uploads/`, and removes the parts of an unfinished multipart upload after a day.
- **The upload queue** hides a received message for a good part of an hour (30 minutes in the local stack), and moves a message to the dead-letter queue after three failed attempts. A build may take longer than that: the consumer receives nothing more until it has finished its batch, so the message is not delivered again meanwhile. On AWS the queue also needs a policy that lets the bucket send to it.
- **The dead-letter queue** keeps messages for 14 days, the most SQS allows. Nothing reads it. An alarm on its size would tell someone to look, and moving its messages back to the upload queue is always safe, since at worst they check archives that are already built.

`scripts/storage-setup.sh` creates all of these with the AWS command-line tool. The local stack's emulator runs it when it starts; on AWS, the same script run once, with credentials, sets the resources up, and only the queue's policy remains.

## In production

- **Never switch on debug mode.** It returns tracebacks in responses and logs at debug level throughout.
- **Leave `SATARA_STORAGE_PUBLIC_URL` unset on AWS,** where S3 has one address for everyone.
- **Give the containers a role** with access to the bucket and the queues, rather than credentials in variables.
- **Put the service behind a proxy or gateway** that enforces the body size limit again and authenticates clients: the endpoints are open to anyone.
