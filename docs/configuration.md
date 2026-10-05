# Configuration

The service and the consumer are configured through environment variables, or a `.env` file in their working directory. Every variable of their own starts with `SATARA_`; other variables are ignored.

A size may carry a unit: `50MiB` is 50 * 1024 * 1024 bytes, `50MB` is 50 * 1000 * 1000, and a bare number is in bytes. A setting outside its bounds, such as a limit of zero, stops the process at start-up.

```shell
docker run --rm -p 8000:8000 -e SATARA_MAX_FILES=20 satara
```

## The direct flow's limits

| Variable                | Default | Limit                                                                   |
|-------------------------|---------|-------------------------------------------------------------------------|
| `SATARA_MAX_FILES`      | 100     | The most files one request may upload; at most 1000, the form parser's. |
| `SATARA_MAX_FILE_SIZE`  | 50 MiB  | The largest size of a single uploaded file.                             |
| `SATARA_MAX_TOTAL_SIZE` | 200 MiB | The largest size of a request body.                                     |

## The deferred flow

The deferred flow is off unless switched on, and then needs storage and a queue, described in [Deployment](deployment.md#storage-and-queues).

| Variable                         | Default                                | Setting                                                           |
|----------------------------------|----------------------------------------|-------------------------------------------------------------------|
| `SATARA_DEFERRED_ENABLED`        | `false`                                | Whether `/archives` is served.                                    |
| `SATARA_DEFERRED_MAX_FILES`      | 1000                                   | The most files one archive may hold; at most 10,000.              |
| `SATARA_DEFERRED_MAX_FILE_SIZE`  | 5 GiB                                  | The largest file; at most 5 GiB, the most one upload to S3 takes. |
| `SATARA_DEFERRED_MAX_TOTAL_SIZE` | 50 GiB                                 | The largest total size of an archive's files; at most 150 GiB.    |
| `SATARA_BUCKET`                  | `satara-archive-deferred-flow-storage` | The bucket that holds the archives.                               |
| `SATARA_QUEUE`                   | `satara-uploads`                       | The queue the bucket notifies of each upload.                     |
| `SATARA_PRESIGNED_URL_LIFETIME`  | 1 hour                                 | How long an upload or download URL stays valid; at most 7 days.   |
| `SATARA_STORAGE_PUBLIC_URL`      | none                                   | The address clients reach storage by, if it differs.              |

A lifetime is an ISO 8601 duration, such as `PT1H`, or hours, minutes and seconds, such as `01:00:00`.

`SATARA_STORAGE_PUBLIC_URL` is needed only when the service reaches storage by an address its clients cannot use, as in the local stack, where the service sees storage as `storage:4566` and a client on the host as `localhost:4566`. A presigned URL's signature covers its address, so the URL must be signed for the address the client will use.

### Access to storage and the queue

The storage address, credentials and region are not settings of the service. The AWS client reads them from its standard variables, `AWS_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_DEFAULT_REGION`, or from the role a container runs with. The region is read from `AWS_DEFAULT_REGION`, not `AWS_REGION`.

## Debug mode

`SATARA_DEBUG=true` pulls all the stops, and is never for production:

- every logger logs at debug level, the libraries' included;
- an unhandled error's 500 response carries its traceback;
- asyncio reports coroutines never awaited and steps that block its event loop;
- each process logs its full settings when it starts.

Every documented refusal keeps the same form in both modes; only an unhandled error's response differs.

## Logs

Logs are written to standard error, one JSON object per line, with the fields `event`, `logger`, `level` and `timestamp`, and others particular to each message. The web server's start-up, error and access lines are in the same form. Records from other libraries, such as the AWS client's warnings, are written as plain text.

At the usual level, info, the service logs what happens once in an archive's life or a process's: its configuration at start-up, an archive created, building it and having built it, and a refused upload by the kind of refusal. A failed attempt that will be retried is a warning, and a final failure an error. What repeats for every message or status check, and anything carrying a client's own data such as file names, is logged only at debug level.

Health checks are left out of the access log: the container checks `/health` every 30 seconds.
