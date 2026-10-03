# Running it

## Configuration

The service is configured through environment variables, or a `.env` file in its working
directory. Other variables are ignored.

| Variable                | Default  | Limit                                                  |
|-------------------------|----------|--------------------------------------------------------|
| `SATARA_MAX_FILES`      | 100      | The most files a single request may upload.            |
| `SATARA_MAX_FILE_SIZE`  | 50 MiB   | The largest size of a single uploaded file.            |
| `SATARA_MAX_TOTAL_SIZE` | 200 MiB  | The largest size of a request body.                    |

A size may carry a unit: `50MiB` is 50 * 1024 * 1024 bytes, `50MB` is 50 * 1000 * 1000, and a
bare number is in bytes. A limit of zero is refused when the service starts, and so are more
than 1000 files, the most the form parser accepts.

```shell
docker run --rm -p 8000:8000 -e SATARA_MAX_FILES=20 satara
```

`SATARA_DEBUG=true` turns on debug logging. Logs are written as one JSON object per line.

## The deferred flow

The deferred flow needs an S3 bucket and an SQS queue, and is off unless switched on:

| Variable                         | Default                                | Setting                                              |
|----------------------------------|----------------------------------------|------------------------------------------------------|
| `SATARA_DEFERRED_ENABLED`        | `false`                                | Whether `/archives` is served.                       |
| `SATARA_DEFERRED_MAX_FILES`      | 1000                                   | The most files one archive may hold.                 |
| `SATARA_DEFERRED_MAX_FILE_SIZE`  | 5 GiB                                  | The largest file; at most 5 GiB, one upload to S3.   |
| `SATARA_DEFERRED_MAX_TOTAL_SIZE` | 50 GiB                                 | The largest total; at most 150 GiB.                  |
| `SATARA_BUCKET`                  | `satara-archive-deferred-flow-storage` | The bucket that holds the archives.                  |
| `SATARA_QUEUE`                   | `satara-uploads`                       | The queue the bucket notifies of each upload.        |
| `SATARA_PRESIGNED_URL_LIFETIME`  | 1 hour                                 | How long an upload or download URL is valid.         |
| `SATARA_STORAGE_PUBLIC_URL`      | none                                   | The address clients reach storage by, if different.  |

A lifetime is an ISO 8601 duration, such as `PT1H`, or hours, minutes and seconds, such as
`01:00:00`, up to 7 days. The storage address, credentials and region are not settings of the
service: the S3 client reads them from the standard variables, `AWS_ENDPOINT_URL`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_DEFAULT_REGION`, or from the role a
container runs with.

`SATARA_STORAGE_PUBLIC_URL` is needed only when the service reaches storage by an address
clients cannot use, as in the local stack below: a presigned URL's signature covers its
address, so the URL must be signed for the address the client will use.

### What storage needs

- The bucket, notifying the queue of every object created under `uploads/`, and removing the
  parts of an unfinished multipart upload after a day. A build stopped before it can abort its
  upload, by a stop signal that outlasts the container's grace period, leaves its parts behind.
- The queue, with a visibility timeout of a good part of an hour (30 minutes in the local
  stack), and a dead-letter queue that takes a message after three failed attempts. A build
  may outlast the timeout: one consumer receives nothing more until it has finished its batch,
  so the message is not delivered again meanwhile.

The local stack's setup step, `compose/storage-setup.sh`, creates all of these. On AWS the
queue also needs a policy letting the bucket send to it. Nothing reads the dead-letter queue:
an alarm on its size would tell someone to look, and moving its messages back to the queue is
always safe.

### The consumer

The consumer builds each archive once its files have arrived. It is a separate process,
started from the same image with another command:

```shell
python scripts/consumer.py
```

It needs the same settings and AWS variables as the service, apart from
`SATARA_STORAGE_PUBLIC_URL`. It serves nothing, so the image's HTTP health check does not
apply to it: it touches `satara-consumer-alive` in the temporary directory every 15 seconds,
and a health check can test that the file is recent. On a stop signal it finishes the batch
of messages in hand and exits. Run one consumer: more would need a lock against building one
archive twice.

### The local stack

`compose.yaml` runs the whole deferred flow locally: MiniStack, an emulator of S3 and SQS;
its setup step; the service, with the flow switched on; and the consumer.

```shell
docker compose up -d --build --wait
```

The service is then at <http://localhost:8000>, and storage at <http://localhost:4566>.
`just test-integration` runs the integration tests against the stack.

## The container

The image is built in two stages: the first installs the locked runtime dependencies, and the
second holds only those and the service's code, without the build tools or the tests.

- The service runs as an unprivileged user, as a single server process listening on port 8000.
  To serve more requests, run more containers.
- A health check calls `GET /health` every 30 seconds.
- On a stop signal the server finishes cleanly.

Uploaded files larger than 1 MiB are written to temporary files under `/tmp` while a request is
read. A container run with a read-only filesystem therefore needs a writable `tmpfs` mounted on
`/tmp`, large enough for the total size limit times the number of requests served at once.

## Checks

The same checks run in two places, through the same `just` recipes and the same locked tool
versions.

| Where                      | When                                  | What                                                                                             |
|----------------------------|---------------------------------------|--------------------------------------------------------------------------------------------------|
| Git hooks, run by prek     | Before each commit                    | File hygiene, then the lint, formatting, dependency and type checks.                             |
| GitHub Actions, `ci.yml`   | Every pull request and push to `main` | The same checks, the tests with the coverage floor, the Docker image, and the integration tests. |
| GitHub Actions, `docs.yml` | Changes to the documentation          | This documentation, built with every warning treated as an error.                                |

The hooks catch problems before a commit exists, but they can be skipped or never installed;
CI cannot. The tests run only in CI, since slow hooks get skipped.

CI does not stop at building the image: it starts it, waits for its health check to pass, and
sends one real upload. A separate job starts the local stack and runs the integration tests
against it, including one that takes an archive through the whole deferred flow.

Dependabot proposes weekly updates for the GitHub Actions, the Docker base images, the images
in the local stack and the Python dependencies, and opens pull requests for security fixes.
